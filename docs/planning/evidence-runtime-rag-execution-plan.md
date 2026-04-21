# 证据层重构执行方案

## 1. 文档定位

这份文档是 [`docs/product/evidence-runtime-rag-direction-prd.md`](../product/evidence-runtime-rag-direction-prd.md) 的执行层展开。

它的作用是：

- 把方向稿收敛成真正可实施的方案
- 明确模块边界、数据模型、接口、阶段切分和验收口径
- 减少后续实现过程中再做高影响架构决策

它不是：

- 最终上线复盘
- 每一行代码的修改清单
- 已经完成的事实描述

当前文档只定义执行方案，不代表代码已经开始或已经完成迁移。

## 2. 发散与收敛结论

这轮方案在发散时实际有三类方向：

- 最轻基础设施：`LanceDB`
- 最平衡正式化：`Qdrant`
- 最省工程接入：`R2R` / 一体化 RAG 后端

结合当前仓库的真实约束，最终收敛结论是：

> 采用 `Qdrant + 项目内自管 Evidence Runtime + text-first 多模态处理` 作为正式执行路线。

同时明确以下结论：

- 不继续沿用 `NotebookLM`
- 不把原生多模态向量作为首阶段硬目标
- 不把 `R2R` 作为当前主线
- 不在第一阶段引入 `LlamaIndex / Haystack`
- 不为了证据层先把主存从 `SQLite` 改成 `Postgres`

## 3. 最终目标架构

## 3.1 总体职责

后续系统职责拆成三层：

### 3.1.1 业务真源层

继续由当前 `SQLite + data/projects/` 承担，保存：

- 项目
- source
- 聊天消息
- 状态沉淀
- artifact
- source chunk ledger
- knowledge base metadata

### 3.1.2 证据索引层

由 `Qdrant` 承担，负责：

- chunk vector 索引
- payload filter
- 项目级 collection 隔离
- retrieval

说明：

- `Qdrant` 不是业务真源
- `Qdrant` 不承担 notebook / 项目管理语义
- `Qdrant` 只服务于 evidence retrieval

### 3.1.3 推理层

继续由 `Claude Agent SDK` 承担，负责：

- 对话回答
- 结构化沉淀
- artifact 生成

证据层不再做最终面向用户的生成式回答。

## 3.2 运行形态

默认采用：

- 本地开发：`Qdrant local mode`
- 服务化部署：`Qdrant server mode`

要求：

- 两种模式共用同一套 `VectorStore` 接口
- 业务层不感知底层是 local 还是 server
- 不因为 local mode 存在，就把它写成只适合开发的临时实现

## 4. 模块设计

执行时把当前 `NotebookLMService` 拆成下面五块。

## 4.1 `SourceNormalizer`

职责：

- 原始 source 落盘后产出统一的标准化结果
- 生成结构化文本、文本片段和定位信息
- 形成可 chunk 的中间表示

输出目标对象：

- `NormalizedDocument`

建议字段：

- `project_id`
- `source_id`
- `source_kind`
- `sections`
- `metadata`
- `summary`

说明：

- 第一阶段允许复用当前 `SourceIngestionService` 的文本抽取能力
- 第二阶段逐步收口到 `Docling`

## 4.2 `ChunkBuilder`

职责：

- 把 `NormalizedDocument` 切成稳定 chunk
- 每个 chunk 必须可回溯到 source 原始定位

chunk 设计要求：

- 不用纯 token 切块作为唯一策略
- 优先保留结构边界：标题、段落、表格、图片描述、音频时间片
- 每个 chunk 都必须带 locator

locator 规则：

- PDF / DOCX：`page`
- XLSX：`sheet + row_range`
- 图片：`image_index`
- 音频：`time_range`
- URL / Markdown：`heading + section_index`

## 4.3 `Embedder`

职责：

- 把 chunk 文本转成向量

设计要求：

- 必须是独立接口，不把 embedding provider 写死在 evidence runtime 里
- 首批支持两类 provider：
  - 远端 embedding provider：作为推荐默认，追求中文检索质量
  - 本地 embedding provider：作为显式可选模式，方便离线和低依赖环境

默认建议：

- 推荐默认：远端 embedding provider
- 本地备用：`FastEmbed`

原则：

- 不做静默 fallback
- 哪个 provider 生效，必须显式体现在 readiness 和配置里

## 4.4 `VectorStore`

职责：

- collection 初始化
- chunk upsert
- chunk delete
- retrieval

默认实现：

- `QdrantVectorStore`

项目隔离策略：

- 每个项目一个 collection

不采用：

- 单全局 collection + 只靠 `project_id` filter 作为唯一隔离方式

原因：

- 产品语义本来就是 project-first
- project-level 重建、清空、验收更清晰
- 后续 source 重建、项目删除和回归测试更容易

## 4.5 `EvidenceRuntime`

职责：

- 项目知识库初始化
- source 索引 / 删除 / 重试
- query 检索
- context packaging
- citations 输出
- readiness 暴露

重要原则：

- `EvidenceRuntime` 返回的是 evidence context package
- 不是用户最终可见答案
- 不再模仿 NotebookLM 的“chat answer”语义

## 5. 多模态执行策略

## 5.1 第一阶段默认支持

第一阶段正式纳入主链路：

- Text
- Markdown
- PDF
- DOCX
- XLSX
- URL

处理方式统一为：

- 先文本化
- 再 chunk
- 再 embedding
- 再 index

## 5.2 第二阶段纳入主链路

第二阶段纳入：

- 图片
- 音频

默认策略：

- 图片：OCR + 可选图片描述，输出文本 chunk
- 音频：ASR 转写，按时间片切 chunk

## 5.3 明确不做

首阶段明确不做：

- 图像向量检索
- 页面截图相似检索
- 图文双向量检索
- 音频向量检索

这些能力只保留后续扩展位，不纳入本次验收。

## 6. 数据模型设计

## 6.1 现有语义调整

当前 `sources` 表和模型里有明显 NotebookLM 语义：

- `notebook_import_mode`
- `parse_status`
- `parse_summary`
- `sync_status`
- `sync_error`

执行方案要求改成更中性的知识库语义。

### 新字段语义

- `notebook_import_mode` -> `index_input_mode`
- `parse_status` -> `normalize_status`
- `parse_summary` -> `normalize_summary`
- `sync_status` -> `index_status`
- `sync_error` -> `index_error`

说明：

- 迁移期允许数据库层临时兼容旧字段
- 对外模型和前端语义必须尽快切换到中性命名

## 6.2 新表 `knowledge_bases`

新增表：

- `project_id`
- `backend`
- `collection_name`
- `status`
- `last_indexed_at`
- `config_json`

用途：

- 取代 `notebook_bindings`
- 保存项目级知识库初始化状态

## 6.3 新表 `source_chunks`

新增表：

- `id`
- `project_id`
- `source_id`
- `chunk_order`
- `modality`
- `content`
- `locator_json`
- `content_hash`
- `embedding_status`
- `indexed_at`

用途：

- 作为本地 chunk ledger
- 保留 citations、去重、重建和调试依据
- 不让 `Qdrant` 成为唯一 chunk 元数据来源

## 6.4 旧表处理

`notebook_bindings` 最终会被废弃，但执行顺序上：

- 第一阶段先新增 `knowledge_bases`
- 第二阶段切业务读写
- 第三阶段删除 `notebook_bindings` 相关代码和文档

## 7. 接口设计

## 7.1 Python 接口

新的 `EvidenceRuntime` 不再只暴露一个 `query()`。

建议最小正式接口：

```python
class EvidenceRuntime(Protocol):
    def ensure_available(self) -> None: ...
    def get_global_readiness(self) -> ProviderReadiness: ...
    def get_project_readiness(self, project_id: str, claude: ProviderReadiness) -> ProjectReadiness: ...
    def ensure_project_knowledge_base(self, project_id: str) -> KnowledgeBaseRecord: ...
    def index_source(self, source_id: str) -> SourceRecord: ...
    def delete_source(self, source_id: str) -> SourceRecord: ...
    def query(self, request: EvidenceQuery) -> EvidenceResult: ...
```

## 7.2 `EvidenceQuery`

建议对象：

- `project_id`
- `question`
- `selected_source_ids`
- `top_k`

要求：

- `selected_source_ids` 必须真正参与 retrieval filter
- 不允许再像当前一样只影响 `source_summaries`

## 7.3 `EvidenceResult`

迁移后建议结构：

- `summary`
- `citations`
- `hits`
- `sync_status`

其中：

- `summary` 是 deterministic evidence context package
- `hits` 是检索命中原始结果
- `citations` 是面向现有聊天链路兼容的最小格式

## 7.4 HTTP API 变化

当前 notebook 相关接口：

- `/api/projects/{project_id}/notebook-binding`
- `/api/projects/{project_id}/notebook-library`
- `/api/projects/{project_id}/notebook-create-and-bind`

执行方案要求最终替换成知识库语义接口，例如：

- `GET /api/projects/{project_id}/knowledge-base`
- `POST /api/projects/{project_id}/knowledge-base/init`
- `POST /api/projects/{project_id}/sources/{source_id}/reindex`

要求：

- 不再暴露 notebook library / notebook binding 产品概念
- 新项目默认由后端自动初始化 knowledge base
- 前端不再需要“创建并绑定 notebook”这类动作

## 8. 聊天链路改造

## 8.1 当前问题

当前聊天链路里，证据层承担了过强的 NotebookLM 产品语义：

- 状态文案是“正在读取 NotebookLM 证据与引用”
- 超时错误写死成 `NOTEBOOKLM_PY`
- evidence summary 默认是 NotebookLM answer

## 8.2 改造后的责任

聊天链路改成：

1. 读取项目状态
2. 收集候选 source
3. 调用 `EvidenceRuntime.query(EvidenceQuery)`
4. 得到 evidence context package + citations
5. 注入 Claude prompt
6. 由 Claude 完成最终回答

## 8.3 首版 retrieval 策略

首版采用：

- dense top-k
- payload filter
- 轻量去重
- 不做 rerank
- 不做 sparse/hybrid

原因：

- 当前优先解决稳定性和接线复杂度
- 不把精度增强项变成首版阻塞项

## 8.4 第二阶段增强

第二阶段再评估：

- rerank
- sparse / hybrid retrieval
- 多向量检索

## 9. 阶段切分

## 9.1 Phase 0：文档与命名冻结

目标：

- 冻结正式方向
- 不再新增 NotebookLM 相关实现

完成标志：

- 方向稿和执行方案文档完成
- 开发时不再把 notebook 语义扩散到新代码

## 9.2 Phase 1：中性抽象与数据层准备

目标：

- 建立 knowledge base 中性语义
- 为 Qdrant 接入做好数据层准备

工作内容：

- 新增 `knowledge_bases`
- 新增 `source_chunks`
- 引入中性模型和类型
- 给旧 notebook 模型和接口标记迁移方向

完成标志：

- 新的中性类型存在
- schema 支持 knowledge base 和 chunk ledger
- 不再新增 notebook 专有模型

## 9.3 Phase 2：Qdrant 接入与 text-first 索引

目标：

- 跑通项目级 collection
- 跑通 source -> normalize -> chunk -> embed -> index

范围：

- Text
- Markdown
- PDF
- DOCX
- XLSX
- URL

完成标志：

- 新项目可自动初始化 knowledge base
- source 可完成索引
- source 删除会同步删除索引
- retry 走 reindex 而不是 notebook sync

## 9.4 Phase 3：query 替换与聊天接线

目标：

- 把聊天 evidence 来源从 NotebookLM 切到新的 retrieval runtime

工作内容：

- `selected_source_ids` 真正参与 filter
- 返回 retrieval citations
- 错误和状态文案改成中性 evidence 语义

完成标志：

- 主聊天链路不再调用 NotebookLM
- citations 来自项目内检索结果
- evidence 超时和失败路径按新 runtime 暴露

## 9.5 Phase 4：前端与产品语义切换

目标：

- 把 UI 上 notebook 语义彻底替换掉

工作内容：

- 工作台 readiness 文案改成 knowledge base 语义
- 去掉 notebook library / binding UI
- source 状态改成 normalize / index 语义

完成标志：

- 前端不再出现 notebook binding 相关产品概念
- source 卡片和运行状态面板都切到新语义

## 9.6 Phase 5：Docling 收口与图片/音频纳入主链路

目标：

- 用统一标准化入口替代当前分散解析逻辑
- 把图片和音频纳入正式链路

完成标志：

- `Docling` 成为主要标准化入口
- 图片 OCR 和音频转写进入正式主链路

## 10. 验收标准

## 10.1 后端能力

- 新项目无需 notebook bind 就能使用 evidence runtime
- source 索引、删除、重试都走新知识库链路
- query 返回真实 citations
- `selected_source_ids` 能影响 retrieval 结果

## 10.2 体验能力

- 聊天证据获取首响明显快于当前 NotebookLM 路线
- evidence 失败时能明确提示，而不是静默降级成假成功
- source 状态文案更贴近真实处理阶段

## 10.3 诚实性

- 不保留误导性 notebook 命名
- 不生成假的 citations
- 没命中时明确暴露未命中
- embedding / qdrant / OCR / ASR 未配置时明确报未配置

## 11. 明确不做

这次执行方案明确不做这些事情：

- 首版原生多模态向量检索
- 首版 rerank
- 首版 sparse / hybrid
- 因证据层改造而顺手把主存迁到 Postgres
- 因证据层改造而引入新的黑盒一体化 RAG 平台
- 继续保留 notebook 产品语义作为正式命名

## 12. 风险与应对

## 12.1 风险：抽象改造面大

应对：

- 先新增中性模型和表，再逐步切业务读写

## 12.2 风险：embedding 质量不稳定

应对：

- provider 显式配置
- 远端推荐、本地可选
- 不做静默 fallback

## 12.3 风险：Docling 变成首阶段阻塞项

应对：

- 首阶段允许沿用当前解析器
- Docling 放到统一标准化收口阶段

## 12.4 风险：前端改动面大

应对：

- 先切后端抽象和 retrieval
- 再统一做前端语义替换

## 13. 当前执行结论

一句话执行结论：

> 这次证据层重构的真正执行路线，是先把系统从 `NotebookLM` 产品语义中解耦，再用 `Qdrant` 建立项目级 retrieval backend，优先跑通 text-first 的 source 索引与 query，最后再把解析层统一收口到 `Docling`。

后续代码实施、接口调整和测试验收，都应以这份执行方案为准展开。

