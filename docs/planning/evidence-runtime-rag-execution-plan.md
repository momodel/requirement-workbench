# 证据层重构执行方案

## 1. 文档定位与适用边界

这份文档是 [`docs/product/evidence-runtime-rag-direction-prd.md`](../product/evidence-runtime-rag-direction-prd.md) 的执行层展开。

它的作用是：

- 把方向稿收敛成可实施的执行方案
- 明确目标架构、模块边界、数据与接口演进、阶段切分、迁移约束和验收口径
- 同时说明新证据链路如何落地，以及旧 `NotebookLM` 路线如何分阶段退场

它不是：

- 逐文件开发清单
- 已经完成的事实描述
- 对旧执行方案做小修小补的修订版

这份文档针对的是“证据层重构”这个专题。它不自动改写仓库里其他一期主文档的全局基线，但会约束这一专题下后续的新增设计和实现。

## 2. 执行结论与上位约束

### 2.1 直接上位约束

就证据层重构这个专题而言，直接上位约束是：

- [`docs/product/evidence-runtime-rag-direction-prd.md`](../product/evidence-runtime-rag-direction-prd.md)

在 [`docs/product/fullstack-phase1-spec.md`](../product/fullstack-phase1-spec.md)、[`docs/planning/fullstack-phase1-todo.md`](./fullstack-phase1-todo.md) 和 `AGENTS.md` 尚未完成同步之前，它们仍然是仓库层面的全局基线。

但从本执行方案定稿开始，任何与证据层重构相关的新增设计、命名、接口和实现，都不得继续沿旧 `NotebookLM` 路线扩散。

### 2.2 执行结论

证据层下一阶段的正式执行路线固定为：

> `Docling + Qdrant + LlamaIndex + 项目内薄适配层 + text-first 多模态策略`

对应结论如下：

- 不继续把 `NotebookLM` 当作证据层正式主路径扩建
- 不继续采用“项目内厚重自管 Evidence Runtime”的路线
- `LlamaIndex` 是正式检索编排层，不再作为“未来可选”
- 多模态首阶段采用 `text-first`，不把原生多模态向量检索设为首版硬目标
- 最终分析、结构化沉淀和 artifact 生成仍由 `Claude Agent SDK` 承担

## 3. 目标架构与模块边界

新证据层的目标不是另一个黑盒知识聊天服务，而是可控的项目级 retrieval 基础设施。

### 3.1 总体分层

后续证据层按下面五层收敛：

#### A. Source Ingestion

负责：

- 原始 source 落盘
- source 类型识别与接入调度
- 标准化流程调起
- 处理状态写入

不负责：

- 检索编排
- 最终回答生成

#### B. Normalization

方向上以 `Docling` 作为统一标准化入口，负责：

- 把 PDF、DOCX、XLSX、URL、图片、音频等输入收敛成结构化文本结果
- 保留可追溯 locator 信息
- 生成可进入 chunk 阶段的中间表示

执行约束：

- `Docling` 是标准化终态，不要求第一阶段就替换掉所有现有解析器
- 在收口完成前，可以有限复用当前解析能力，但不能把零散解析器继续扩张成新的长期方案

#### C. Retrieval Orchestration

由 `LlamaIndex` 承接，负责：

- 文档对象组织
- chunk ingestion
- index write orchestration
- query orchestration
- citation 所需 metadata 保留和透传

执行约束：

- 这里不再继续自研通用的 chunk / retrieve / summarize / citations 编排
- 项目代码只保留必要的项目语义适配，不重造完整 RAG orchestration

#### D. Retrieval Storage

由 `Qdrant` 承担，负责：

- 向量存储
- payload / metadata 过滤
- 项目级隔离
- 检索能力承接

执行约束：

- `Qdrant` 不是业务真源
- `Qdrant` 不承载项目状态语义、UI 语义和 notebook 风格管理语义

#### E. Project Retrieval Adapter

项目内只保留一层薄适配层，负责：

- 把 `project_id` 映射到 collection / namespace / filter
- 组织 source 的 index / delete / reindex 项目级流程
- 把 retrieval 结果转换成当前聊天链路可消费的 `summary + citations + hits + status`
- 把 readiness、错误、未命中、未初始化等状态回写到项目模型和 UI 所需语义

### 3.2 明确边界

后续实现必须守住下面三条边界：

- 证据层是检索服务，不是最终面向用户的回答服务
- 项目内适配层是薄层，不是新的厚重自管 RAG 平台
- `Claude Agent SDK` 继续负责最终分析输出、状态沉淀和 artifact 生成

## 4. 多模态策略与标准化收口原则

### 4.1 第一阶段默认策略

首阶段统一采用 `text-first`：

- 文本、Markdown、DOCX、PDF：转文本
- XLSX：转结构化文本
- URL：抓正文并转文本
- 图片：OCR + 可选图片描述
- 音频：转写 + 时间片切分

再统一走：

- normalize
- chunk
- embedding
- retrieval

### 4.2 为什么不是原生多模态优先

当前优先级是：

- 项目级知识库稳定可控
- 聊天主链路稳定接线
- citation 和失败路径清晰可解释

因此，图像向量检索、图文双向量检索、音频向量检索都不作为首版硬目标。

### 4.3 标准化收口原则

标准化层后续统一收口到 `Docling`，但执行顺序上：

- 不要求 `Docling` 成为第一阶段阻塞项
- 允许先打通 `Qdrant + LlamaIndex + 薄适配层`
- 再逐步把现有 PDF / DOCX / XLSX / URL / 图片 / 音频解析能力收口到 `Docling`

### 4.4 locator 约束

每个 chunk 都必须具备可解释 locator，至少满足：

- PDF / DOCX：`page`
- XLSX：`sheet + row_range`
- 图片：`image_index` 或 OCR 区块定位
- 音频：`time_range`
- URL / Markdown：`heading + section_index`

如果某类 source 做不到稳定 locator，就不能把它包装成“完整 citation 已支持”。

## 5. 项目内接口设计

### 5.1 设计原则

项目内接口的目标是提供项目语义和状态语义，不是把证据层重新包装成另一个 notebook 风格对话服务。

新的项目内适配层至少要覆盖下面这些能力：

- 全局可用性检查
- 项目级 readiness 查询
- 项目知识库初始化
- source 索引
- source 删除
- source 重建索引
- evidence query

### 5.2 建议最小接口

执行方案建议按下面这组最小职责设计项目内接口：

```python
class EvidenceRuntime(Protocol):
    def ensure_available(self) -> None: ...
    def get_global_readiness(self) -> ProviderReadiness: ...
    def get_project_readiness(self, project_id: str) -> ProjectReadiness: ...
    def ensure_project_knowledge_base(self, project_id: str) -> KnowledgeBaseRecord: ...
    def index_source(self, source_id: str) -> SourceRecord: ...
    def delete_source(self, source_id: str) -> SourceRecord: ...
    def reindex_source(self, source_id: str) -> SourceRecord: ...
    def query(self, request: EvidenceQuery) -> EvidenceResult: ...
```

这里的约束是接口语义，不要求最终代码逐字照抄。

### 5.3 `EvidenceQuery`

建议最小字段：

- `project_id`
- `question`
- `selected_source_ids`
- `top_k`

必要约束：

- `selected_source_ids` 必须真实进入 retrieval filter
- 不允许只影响 source 摘要展示，却不影响实际召回

### 5.4 `EvidenceResult`

建议最小结构：

- `summary`
- `citations`
- `hits`
- `status`
- `errors`

语义要求：

- `summary` 是 deterministic evidence context package，不冒充最终结论
- `citations` 必须来自真实 retrieval hit
- `hits` 保留原始命中信息，便于调试、追溯和失败解释
- `status` / `errors` 必须能表达未初始化、未命中、超时、provider 失败等状态

## 6. 数据模型与状态语义迁移

### 6.1 现有 source 语义迁移

当前 `sources` 模型和表中有明显 notebook 语义，例如：

- `notebook_import_mode`
- `parse_status`
- `parse_summary`
- `sync_status`
- `sync_error`

后续应迁移为中性的知识库语义，例如：

- `notebook_import_mode` -> `index_input_mode`
- `parse_status` -> `normalize_status`
- `parse_summary` -> `normalize_summary`
- `sync_status` -> `index_status`
- `sync_error` -> `index_error`

执行约束：

- 数据库层允许在迁移期临时兼容旧字段
- 对外接口、前端状态、文档说明必须尽快切换到中性语义
- 不允许继续把旧字段语义扩散成正式产品命名

### 6.2 新增 `knowledge_bases`

建议引入项目级知识库记录，至少包含：

- `project_id`
- `backend`
- `status`
- `collection_name`
- `last_indexed_at`
- `config_json`

用途：

- 替代 `notebook_bindings`
- 记录项目级 knowledge base 初始化状态
- 作为项目 readiness 的核心数据来源之一

### 6.3 新增 `source_chunks`

建议引入本地 chunk ledger，至少包含：

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

- 为 citation、去重、重建、调试保留本地元数据
- 不让 `Qdrant` 成为唯一 chunk 元数据来源

### 6.4 三层状态语义

后续状态要明确拆成三层：

#### A. global readiness

例如：

- `Qdrant` 是否可用
- embedding provider 是否已配置
- normalization runtime 是否可用

#### B. project readiness

例如：

- knowledge base 是否已初始化
- 当前项目是否存在可检索 source
- 是否存在索引失败 source

#### C. source lifecycle

例如：

- `uploaded`
- `normalizing`
- `normalized`
- `chunked`
- `embedding`
- `indexed`
- `index_failed`

## 7. HTTP API 与前端语义调整方向

### 7.1 后端 API 方向

后续应逐步淘汰 notebook 风格接口，例如：

- `GET /api/projects/{project_id}/notebook-binding`
- `GET /api/projects/{project_id}/notebook-library`
- `POST /api/projects/{project_id}/notebook-create-and-bind`

替换为中性的 knowledge base / reindex 语义，例如：

- `GET /api/projects/{project_id}/knowledge-base`
- `POST /api/projects/{project_id}/knowledge-base/init`
- `POST /api/projects/{project_id}/sources/{source_id}/reindex`

### 7.2 产品语义方向

前端不再继续暴露这些概念作为正式产品动作：

- notebook binding
- notebook library
- create and bind notebook
- sync to notebook

应切换成：

- knowledge base readiness
- 自动初始化项目知识库
- source normalize / index / reindex
- evidence availability / failure state

### 7.3 新项目初始化原则

新项目默认由后端自动初始化 knowledge base。

不再把“创建并绑定 notebook”这类动作交给用户，也不把它作为工作台主路径前提。

## 8. 聊天链路接线原则

### 8.1 责任重排

聊天主链路调整为：

1. 读取项目状态
2. 收集候选 source
3. 调用 `EvidenceRuntime.query(EvidenceQuery)`
4. 获取 evidence context package + citations + hits
5. 把 evidence 上下文注入 `Claude Agent SDK`
6. 由 Claude 完成最终回答、结构化沉淀和 artifact 决策

### 8.2 首版 retrieval 策略

首版以稳定性为先，采用：

- dense top-k
- payload filter
- 轻量去重
- 不做 rerank
- 不做 sparse / hybrid

### 8.3 失败处理原则

聊天可以在证据层失败时降级继续，但必须明确说明：

- 当前没有可用 grounding
- 当前没有可用 citations
- 当前失败发生在哪个阶段

不允许：

- 用旧 `NotebookLM` 成功结果静默掩盖新链路失败
- 在 retrieval 未命中时伪造 grounding
- 在 provider 不可用时伪造 citations

## 9. 分阶段实施计划

### Phase 0：方向冻结与扩散止损

目标：

- 冻结新方向
- 停止旧 `NotebookLM` 路线继续扩散

允许保留：

- 已存在的 `NotebookLM` 代码仅作为迁移过渡链路保留

禁止继续新增：

- 任何新的 notebook 风格产品语义、接口、命名和主路径依赖

完成标志：

- 方向稿与执行方案定稿
- 后续新增实现不再朝旧路线扩建

### Phase 1：中性语义与数据层准备

目标：

- 建立 knowledge base 中性语义
- 为新 retrieval 路线准备数据层与状态层

工作内容：

- 新增 `knowledge_bases`
- 新增 `source_chunks`
- 引入中性模型和状态类型
- 为旧 notebook 模型标记迁移方向

允许保留：

- 数据库层对旧字段的临时兼容

禁止继续新增：

- 面向外部的新 notebook 专有模型和字段语义

完成标志：

- schema 支撑 knowledge base 和 chunk ledger
- 对外新语义已可用

### Phase 2：Qdrant + LlamaIndex 的 text-first 索引主链路

目标：

- 跑通 `source -> normalize -> chunk -> embed -> index`
- 建立项目级 knowledge base 的正式索引主路径

纳入首阶段主链路的 source 类型：

- Text
- Markdown
- PDF
- DOCX
- XLSX
- URL

允许保留：

- 部分现有解析逻辑，直到 `Docling` 收口完成

禁止继续新增：

- “不引入 LlamaIndex”的旧结论
- notebook sync 语义作为新索引链路的正式说法

完成标志：

- 新项目可自动初始化 knowledge base
- source 可完成索引
- source 删除会同步删除索引
- source 失败重试走 `reindex`

### Phase 3：query 接管与聊天链路切换

目标：

- 把聊天 evidence 来源从旧 `NotebookLM` query 切到新 retrieval runtime

工作内容：

- `selected_source_ids` 真实进入 filter
- retrieval citations 接入聊天链路
- evidence 状态和错误文案切换到中性语义

允许保留：

- 为验证迁移正确性的短期双跑对照

禁止继续新增：

- 把旧 `NotebookLM` query 写成主链路默认路径
- 把 retrieval 失败静默包装成旧链路成功

完成标志：

- 主聊天链路不再依赖 NotebookLM query
- citations 来自新检索结果
- evidence 未命中、超时、失败路径都可如实暴露

### Phase 4：UI 与产品语义切换

目标：

- 把工作台残留的 notebook 产品语义彻底切掉

工作内容：

- readiness 面板改成 knowledge base 语义
- 去掉 notebook library / binding UI
- source 状态改成 normalize / index / reindex 语义

允许保留：

- 内部迁移代码中的旧实现引用，前提是不再暴露给用户

禁止继续新增：

- 面向用户的 notebook 概念和手工 notebook 绑定流程

完成标志：

- 前端不再暴露 notebook binding 相关产品概念
- 工作台的证据层语义与真实运行时一致

### Phase 5：Docling 收口与多模态补齐

目标：

- 用统一标准化入口替代分散解析逻辑
- 把图片和音频纳入正式 text-first 链路

工作内容：

- 逐步收口到 `Docling`
- 图片走 OCR + 可选描述
- 音频走转写 + 时间片 chunk
- 统一 locator / citation 规则

允许保留：

- 个别过渡解析器短期存在，直到对应 source 类型完成迁移

禁止继续新增：

- 新的长期分散解析分支

完成标志：

- `Docling` 成为主要标准化入口
- 图片和音频进入正式主链路

### Phase 6：旧 NotebookLM 路线退场

目标：

- 让旧 `NotebookLM` 路线退出主链路并最终删除

工作内容：

- 停掉聊天主链路对 `NotebookLM` 的依赖
- 删除旧接口、旧文案、旧命名和旧表依赖
- 清理误导性注释和残留脚本说明

允许保留：

- 仅限短期只读兼容或迁移校验用途

禁止继续新增：

- 任何把旧路径包装成正式路线的说法和实现

完成标志：

- 主链路零依赖 `NotebookLM`
- 文档、UI、接口、命名中不再把旧路径写成正式方案

## 10. NotebookLM 兼容期与退场原则

### 10.1 兼容期允许存在什么

在迁移期内，可以临时保留：

- 已有 `NotebookLM` provider 接线
- 与旧数据兼容所需的数据库字段或接口层兼容逻辑
- 为迁移验证做的新旧双跑对照

但这些都只能被视为迁移脚手架，不再视为继续建设对象。

### 10.2 兼容期禁止什么

兼容期内仍然禁止：

- 新增 notebook 风格产品语义
- 在新代码中继续把 notebook binding / library 当作正式领域模型
- 用旧链路静默兜底掩盖新链路问题

### 10.3 退场顺序

旧路线的退场顺序固定为：

1. 先停主聊天链路依赖
2. 再切掉前端 UI 与 readiness 文案
3. 再删除后端旧接口、旧模型读写和旧 provider 接线
4. 最后清理文档、脚本、注释和误导性命名

## 11. 验收标准

### 11.1 架构验收

- 证据层正式架构已经落到 `Docling + Qdrant + LlamaIndex + 项目内薄适配层`
- 项目内层没有膨胀成新的厚重自研 RAG 平台
- `Claude Agent SDK` 仍是最终分析与 artifact 生成主体

### 11.2 主链路验收

- 新项目无需 notebook bind 即可使用项目级 knowledge base
- source 能完成 `normalize -> chunk -> embed -> index`
- 聊天 query 主链路来自新 retrieval runtime
- `selected_source_ids` 真实影响 retrieval 结果
- citations 来自真实 retrieval hits

### 11.3 失败路径验收

- `Qdrant` 不可用、embedding 未配置、normalization 失败、query 超时、未命中都能被明确暴露
- 聊天在证据层失败时可以降级继续，但必须明确说明当前无 grounding / citations
- 不保留伪造 citations、伪造 grounding、静默 fallback 假成功

### 11.4 产品语义验收

- 前端不再暴露 notebook binding / notebook library / sync to notebook 语义
- source 状态、重试动作、readiness 面板都切换到 normalize / index / knowledge base 语义
- UI 语义与后端真实运行时一致

### 11.5 退场验收

- 主聊天链路、项目 readiness、source 主状态都不再依赖旧 `NotebookLM` 路线
- 旧接口、旧文案、旧命名进入删除或只读兼容阶段
- 文档中不再把旧路线描述成正式主方案

只要主聊天链路还依赖 `NotebookLM`，就不能把证据层迁移说成“已完成”。

## 12. 文档联动与后续同步顺序

后续文档同步顺序固定为：

1. 先定稿这份执行方案
2. 再同步更新：
   - [`docs/product/fullstack-phase1-spec.md`](../product/fullstack-phase1-spec.md)
   - [`docs/planning/fullstack-phase1-todo.md`](./fullstack-phase1-todo.md)
   - `AGENTS.md`
3. 再开始代码层迁移、接口调整和前后端语义切换
4. 在聊天主链路、前端语义和失败路径都切换完成后，再进入旧路线删除阶段

执行约束：

- 在正式主文档完成同步前，仓库层面的全局基线仍以现有一期文档为准
- 但就证据层重构专题而言，新增设计与实现必须遵守方向稿和本执行方案，不得再朝旧 `NotebookLM` 路线扩展

## 13. 明确不做

这次执行方案明确不做这些事情：

- 首版原生多模态向量检索
- 首版 rerank
- 首版 sparse / hybrid retrieval
- 因证据层改造而顺手把主存迁到 Postgres
- 因证据层改造而引入新的黑盒一体化 RAG 平台
- 继续保留 notebook 产品语义作为正式命名
- 把证据层重新做成面向用户的完整回答服务

## 14. 风险与应对

### 14.1 风险：抽象改造面大

应对：

- 先新增中性模型和状态层，再逐步切业务读写
- 不在一个阶段里同时完成所有接口、数据和 UI 切换

### 14.2 风险：embedding 质量或 provider 稳定性不足

应对：

- provider 显式配置
- 推荐默认与可选本地模式分开说明
- 不做静默 fallback

### 14.3 风险：Docling 变成首阶段阻塞项

应对：

- 首阶段允许沿用现有解析能力
- 把 `Docling` 收口放到明确的后续阶段完成

### 14.4 风险：前端和产品语义切换面大

应对：

- 先切后端抽象与 retrieval 主路径
- 再统一替换 UI 语义
- 避免在迁移中长期维持双套产品语义

### 14.5 风险：兼容期无限拉长

应对：

- 单独设置 `NotebookLM` 退场阶段
- 把“主聊天链路已切走”作为迁移完成的硬门槛

## 15. 当前执行总结

一句话总结：

> 这次证据层重构的正式执行路线，不是继续依赖外部知识聊天服务，也不是继续写厚重的项目内 retrieval runtime，而是用 `Docling + Qdrant + LlamaIndex` 构成清晰的标准化、存储和检索编排层，再由项目内薄适配层承接项目语义、状态回写和接口对齐，并把最终分析权继续留给 `Claude Agent SDK`。

后续代码实施、接口调整、文档联动和迁移验收，都应以这份执行方案为准展开。
