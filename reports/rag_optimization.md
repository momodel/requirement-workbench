# RAG 优化评测

## 评测设置

跑了两份数据：
- **Seed 集**：`seed-reconciliation` 自带的 4 份业财对账物料（每份 200–400 字符），12 条 query，`backend/scripts/rag_eval.py`
- **真实集**：`data/projects/project-e247c8192d` 和 `project-c46b1bf88f` 下面 7 份真实业务文档（项目背景、补充说明、微信群整理、会议纪要、客户访谈纪要等，760–1850 字符/份），14 条 query，`backend/scripts/rag_eval_real.py`

指标：
- `hit@k` — top-k 中是否至少有一条 chunk 来自期望 source
- `MRR` — 第一个命中 source 的排名倒数平均
- 每个配置用独立临时 Qdrant 路径，互不污染

## 结果（seed 集，12 query）

| 配置 | hit@1 | hit@3 | MRR | 单查询耗时 |
|---|---|---|---|---|
| baseline（bge-small-en，chunk 800/0，无 rerank） | 0.333 | 1.0 | 0.639 | 6 ms |
| 换中文 embedding（bge-small-zh） | 0.667 | 1.0 | 0.833 | 3 ms |
| + 改进分片（500/120 overlap，句子级切） | 0.667 | 1.0 | 0.833 | 3 ms |
| + reranker（bge-reranker-base，召回 20 → 重排到 6） | **0.917** | 1.0 | **0.958** | 568 ms |

## 结果（真实业务集，14 query）

| 配置 | hit@1 | hit@3 | hit@6 | MRR | 单查询耗时 |
|---|---|---|---|---|---|
| baseline（bge-small-en，800/0） | **0.071** | 0.786 | 0.929 | 0.411 | 5 ms |
| 换中文 embedding | 0.571 | 1.0 | 1.0 | 0.774 | 3 ms |
| + 改进分片（500/120） | 0.786 | 0.929 | 1.0 | 0.875 | 4 ms |
| + reranker（召回 20 → 重排到 6） | **1.0** | 1.0 | 1.0 | **1.0** | **2.0 s** |

> 真实集上 baseline hit@1 只有 7%（14 题里只有 1 题 top-1 命中），MRR 0.41。也就是说当前线上配置在中文真实数据上**第一名几乎全错**，靠扩大 top-k 才能勉强把正确答案拉进上下文。其中 "演示用的对账案例和产品本身是什么关系" 这一条 baseline 直接 top-6 全错（rank=None）。换成 zh embedding 之后立刻全部进 top-6，加上 reranker 14 题全部 top-1 命中。

## 解读

1. **当前 baseline 在中文真实数据上是不可用状态**。真实集 hit@1 只有 7%，意味着用户问 14 个问题里有 13 个 top-1 是错的。线上能跑下去靠的是 LLM 拿着错位的 top-6 上下文还能蒙对答案 + 用户没意识到检索质量的损耗。
2. **换中文 embedding 是最大杠杆**。真实集 hit@1 7% → 57%，MRR +88%；seed 集 33% → 67%。这一项基本是免费的（onnx 本地推理，反而比英文模型还快一点）。
3. **改进分片在真实数据上看到了收益**。hit@1 从 57% → 79%，chunks 从 7 涨到 11，意味着原本被压缩在一个大 chunk 里的多个主题被分开了，向量召回能更精确地命中相关段落。在 seed 集上看不出是因为 seed 文档太短（< 500 字），根本不触发二次切分。
4. **reranker 把残留问题扫干净**。真实集直接做到 hit@1=100%、MRR=1.0；seed 集 92%。代价是单查询从 4ms → 2s（真实集召回 11–20 个 chunk 都要 rerank）；分析师场景的交互延迟可接受，对话密度高时可以做缓存或异步预热。
5. baseline 在中文上的失败模式很一致：英文 embedding 把整段中文当成不规则 token 来处理，对长 chunk 的"主题"比对短答的"信息点"更敏感。所以经常出现"客户初访纪要"或"requirement-flow-evidence"这种通用名称的文档霸占前几名，而真正含答案的文档反而被挤到 top-6 之外。换中文模型后这个失败模式立刻消失。

## 落地改动

- `backend/app/config.py` — 新增 `embedder_model` / `reranker_model` / `evidence_recall_top_k` / `chunk_size` / `chunk_overlap` 字段，env 默认：
  - `REQUIREMENT_WORKBENCH_EMBEDDER_MODEL=BAAI/bge-small-zh-v1.5`
  - `REQUIREMENT_WORKBENCH_RERANKER_MODEL=`（默认空，置空就关 reranker）
  - `REQUIREMENT_WORKBENCH_EVIDENCE_RECALL_TOP_K=20`
  - `REQUIREMENT_WORKBENCH_CHUNK_SIZE=500`、`REQUIREMENT_WORKBENCH_CHUNK_OVERLAP=120`
- `backend/app/services/vector_store.py` — embedding 模型按 settings 注入；新增 `_get_reranker`，`query()` 在配了 reranker 时先取 `recall_top_k` 再重排。
- `backend/app/services/evidence_indexing.py` — 切分支持 `chunk_size`/`chunk_overlap` 参数；超长段落按中英文句末标点（`。！？!?；;\n`）切句子再合并；相邻 chunk 之间从前一段尾部拷 `chunk_overlap` 字符做 overlap。
- `backend/app/services/evidence_runtime.py` — 把 settings 透传给 `prepare_source_chunks`。

## 注意：必须 reindex

新默认 embedding `bge-small-zh-v1.5` 是 **512 维**，旧的 en 模型是 **384 维**。已存在的 Qdrant collection 维度不匹配，必须删掉重建：

```bash
rm -rf data/qdrant
# 启动后从 UI 触发 reindex，或调 reindex_source 接口
```

或者通过 env 把 embedding 模型固定回旧值保留兼容：
```bash
REQUIREMENT_WORKBENCH_EMBEDDER_MODEL=BAAI/bge-small-en-v1.5
```

## 还能继续做的

- **真实长文档评测**：seed 数据太短，看不出 chunk/overlap 影响。需要弄一份带长 PDF 或长 markdown 的样本集再测一次，才能确认 chunk_size=500/overlap=120 是不是最优。
- **reranker 的延迟优化**：568 ms 在交互场景能接受，但批量评估时累加。可以考虑结果缓存（query+chunk_id → score）或换更小的 reranker（`jina-reranker-v1-tiny-en` 是英文，中文场景没替代品；`bge-reranker-base` 已经是较小档）。
- **多语言模型选项**：对于混合中英资料，可以加个 `intfloat/multilingual-e5-large`（1024 维）或 `jinaai/jina-embeddings-v3` 的预设。
- **混合检索**：BM25 + 向量做 RRF 融合，对带具体编号（如 `ORD-1003`）的查询更稳。Qdrant 的 sparse/dense hybrid 已经支持，能在不上 Elasticsearch 的前提下实现。
