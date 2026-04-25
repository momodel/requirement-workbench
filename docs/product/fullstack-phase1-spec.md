# 客户需求转译台 全栈一期 Spec

## 1. 文档定位

这份文档描述的是 `全栈一期` 现在要重做成什么样，不是对当前代码现状的背书。

当前仓库里已经有一批前后端代码，但它们只能视为探索残留，不能当成一期实现基线，原因有三点：

- 技术栈没有对齐已经确认的方案，尤其是前端没有切到 `shadcn/ui + Tailwind` 的新版工作台实现，后端也没有真正接上 `Claude Agent SDK`
- 一些类名和服务名带有误导性，名字像真实 provider，实际还是本地 stub 或 mock 风格
- 产品感和交互质量退步，当前工作台弱于 `archive/legacy-demo/` 的整体感觉

因此，这个一期 spec 的前提很明确：

- 在当前仓库内继续做
- 旧探索代码不自动视为可沿用实现
- 是否复用旧代码，以是否符合本 spec 为准
- `archive/legacy-demo/` 是新版前端产品感和交互基线，不是后端流程模板

## 2. 一期目标

一期要做的是一个真实可跑的 `客户需求转译台` 本地单用户版本。

主产品仍然是通用需求转译台，`业财逐笔对账` 只是默认 seed project，用来保证演示和开发过程有一条稳定主线。

一期完成后，系统应能跑通这条真实链路：

1. 创建或打开一个项目
2. 上传或导入资料
3. 资料经过标准化和 项目内 RAG 证据接入
4. 用户在工作台中持续对话
5. 主智能体基于项目状态和证据推进分析
6. 右侧项目状态持续更新
7. 关键轮次自动生成版本快照
8. 用户可以触发文档稿、页面方案、交互稿生成
9. 页面方案和交互稿以可交互 HTML 预览

一期不做这些内容：

- 登录、多用户、权限系统
- 在线部署稳定性工程
- 回滚、diff、协作审批流
- 真正的业务系统对接
- 真正的财务对账执行引擎

## 3. 一期成功标准

一期不是“页面能打开”就算完成，而是要同时满足下面几类要求。

### 3.1 产品要求

- 工作台必须是三栏分析台，不是后台表单页
- 中间聊天区是主角，左侧资料、右侧状态都围绕分析过程服务
- 新版前端至少恢复到 `archive/legacy-demo` 的产品感和演示可讲性
- `业财逐笔对账` 这条案例要能自然讲通，从模糊诉求到交付物生成不能靠硬切页面来解释

### 3.2 技术要求

- 前端采用 `React + Vite + TypeScript + shadcn/ui + Tailwind`
- 后端采用 `FastAPI + SQLite + SSE`
- 主智能体走真实 `Claude Agent SDK`
- 证据层走真实 `Docling + Qdrant + LlamaIndex` 工作流
- Qdrant 存储、embedding 依赖和 source 索引状态必须收口到项目内配置，不能默认依赖用户家目录
- `requirement-analysis-methodology` 不能只作为名词提示存在，必须以可执行规则影响主 agent prompt、状态沉淀、追问优先级和 artifact 触发
- 中间不得用“名字像真 provider、实际是本地拼字串逻辑”的实现冒充正式链路

### 3.3 运行要求

- 前后端分开启动
- 无需一键脚本
- 本地能稳定完成一个项目从资料接入到 artifact 生成的完整流程

### 3.4 诚实性要求

- 未配置 provider 就明确报未配置
- provider 调用失败就明确显示失败
- 不把 fallback mock 伪装成正式结果
- 不在 UI 或文档里把 stub 行为写成“已接入 Claude / 已接入 项目知识库”

## 4. 产品形态

### 4.1 顶层对象

系统的顶层对象是 `Project`，不是 `Conversation`。

首页展示：

- 项目列表
- 创建项目入口
- 默认 seed project：`业财逐笔对账`

### 4.2 主工作台

主路由固定为 `/projects/:projectId/workbench`。

工作台维持三栏结构：

- 左栏 `Sources`
- 中栏 `Chat`
- 右栏 `Project State`

布局原则：

- 顶部是固定的轻量项目头和状态条
- 三栏主体固定在视口内
- 各栏内部独立滚动
- 中栏聊天区优先级最高，宽度最大
- 页面方案和交互稿使用居中大预览层，不塞进窄抽屉

### 4.3 左栏 Sources

左栏负责真实资料工作台，不是阶段卡片区。

应包含：

- source 列表
- 上传入口
- URL / 文本导入入口
- 解析状态
- 项目知识库索引状态
- 已引用标记
- 当前选中 source 的摘要浮卡

交互要求：

- 点击 source 时展示摘要浮卡
- 浮卡定位在被点击项右侧
- 浮卡打开后内容滚动位置回到顶部
- 浮卡不能靠半透明遮罩糊弄过去，信息要清晰可读

### 4.4 中栏 Chat

中栏是整个系统的主界面。

应包含：

- 用户消息
- assistant 流式输出
- 引用 source 芯片
- 当前轮分析状态
- artifact 生成状态

聊天体验要求：

- 历史消息可完整回看
- 新消息到来时自动滚到最新位置
- 中栏之外不跟着整体滚动
- 不能做成静态卡片拼盘，要体现 AI 逐轮推进、追问、确认、修正、沉淀

### 4.5 右栏 Project State

右栏是项目状态总集，不按页面切阶段。

固定分区：

- 当前理解
- 待确认项
- 已确认项
- 冲突项
- MVP
- 版本快照
- 交付物

交互要求：

- patch 到来后即时更新
- 文档稿在右侧抽屉查看
- 页面方案和交互稿点击后进入大预览层
- 版本快照展示摘要和触发原因，不做复杂 diff

## 5. 默认案例

默认 seed project 为 `集团业财逐笔对账需求分析`。

案例设定固定为：

- 上游业务系统：订单系统或结算系统
- 财务侧：财务系统中与业务系统对应科目的金额
- 对账粒度：逐笔对账
- 核心冲突：业务字段到财务科目映射口径不一致

这个案例的作用是：

- 作为默认演示主线
- 作为 seed data 和 UI 验收样本
- 作为 provider 接入联调时的固定回归案例

## 6. 前端实现规格

### 6.1 技术栈

前端采用：

- `React`
- `Vite`
- `TypeScript`
- `Tailwind CSS`
- `shadcn/ui`

状态层可以使用 `Zustand`，但不是强制单独目标；是否引入以工作台状态复杂度为准。

### 6.2 视觉和交互基线

新版前端以 `archive/legacy-demo` 为直接产品参考。

这句话的意思是：

- 可以改样式
- 可以改实现方式
- 但新版至少要恢复到旧 demo 那种分析工作台的产品感
- 不能退成配置台、表单页或管理后台味道

直接参考范围包括：

- 页面信息密度
- 三栏关系
- 聊天主导感
- 工作台而不是步骤页的体验
- 交付物预览方式

不要求一比一照抄：

- 旧 demo 的 mock 数据结构
- 旧 demo 的阶段页路由
- 旧 demo 的后端流程

### 6.3 前端主模块

前端主工程落在 `frontend/`。

建议结构：

- `frontend/src/app/`
- `frontend/src/features/projects/`
- `frontend/src/features/workbench/`
- `frontend/src/features/sources/`
- `frontend/src/features/chat/`
- `frontend/src/features/project-state/`
- `frontend/src/features/artifacts/`
- `frontend/src/lib/api/`
- `frontend/src/lib/types/`

当前根目录旧前端资产、`archive/legacy-demo/frontend-vite-demo/` 和历史 HTML 原型只作参考，不作为一期主实现。

## 7. 后端实现规格

### 7.1 技术栈

后端采用：

- `FastAPI`
- `SQLite`
- `Pydantic`
- `SSE`

后端主工程落在 `backend/`。

### 7.2 职责

后端负责：

- 项目 CRUD
- source 入库
- source 标准化
- 项目知识库索引和检索
- 聊天流式接口
- 项目状态写入与聚合
- 版本快照
- artifact 生成与落盘

### 7.3 建议目录

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `backend/app/schema.sql`
- `backend/app/models.py`
- `backend/app/routes/projects.py`
- `backend/app/routes/sources.py`
- `backend/app/routes/chat.py`
- `backend/app/routes/versions.py`
- `backend/app/routes/artifacts.py`
- `backend/app/services/agent_runtime.py`
- `backend/app/services/evidence_runtime.py`
- `backend/app/services/source_ingestion.py`
- `backend/app/services/project_state.py`
- `backend/app/services/artifact_generation.py`
- `backend/app/services/seed_projects.py`

### 7.4 数据目录

- `data/sqlite/`
- `data/projects/<project-id>/sources/`
- `data/projects/<project-id>/artifacts/`

## 8. 运行时与 provider 约束

### 8.1 Claude Agent SDK

一期选定 `Claude Agent SDK` 作为主智能体运行时。

这里的“接入 Claude Agent SDK”指的是：

- 代码真实依赖 SDK
- 运行时真实调用 SDK
- 主 assistant 输出来自 SDK 结果

不算合格接入的情况：

- 本地规则拼接文本，但类名叫 `ClaudeAgentRuntime`
- 预置脚本响应，再包一层 SDK 风格接口
- 用 mock provider 跑主流程，却在文档和 UI 里写成“Claude 已接入”

### 8.2 项目知识库

一期选定 `Docling + Qdrant + LlamaIndex` 作为资料理解接入路径。

这里的“接入 项目知识库”指的是：

- 有真实的 项目知识库 操作链路
- 项目可以通过正式能力初始化自己的 knowledge base
- source 能真实进入 项目知识库 工作流
- grounded summary 和 citations 来自真实 项目知识库 查询

不算合格接入的情况：

- 本地对文件做摘要，然后命名成 `EvidenceRuntime`
- 伪造 citation 结构
- 用本地 mock 证据结果冒充 项目知识库 输出

### 8.3 适配层

为了不把 provider 写死，后端保留两个接口：

- `AgentRuntime`
- `EvidenceRuntime`

但“保留适配接口”不代表可以长期用假的默认实现充当正式实现。

一期主路径就是：

- `AgentRuntime -> Claude Agent SDK`
- `EvidenceRuntime -> 项目内 RAG workflow`

## 9. 项目级 Skills

一期保留三个后端 CAS project skills。

后端 CAS skills 以 `backend/.claude/skills/` 为正式维护位置，并由 `Claude Agent SDK` 在 `backend/` 作用域自动发现。

### 9.1 requirement-analysis-methodology

这个 skill 的定位是：

- 给主智能体和开发者提供需求分析方法参考
- 约束如何做 intake、澄清、冲突识别、状态沉淀、artifact 触发
- 作为 prompt 和分析流程的参考底稿

一期里它必须进一步落到这些可执行层面：

- 明确何时用 `BABOK` 视角做 intake、范围、约束和风险抽取
- 明确何时用 `JTBD` 视角区分页面诉求和真实任务
- 明确何时用 `Event Storming` 视角还原流程、事件、系统边界和异常
- 明确不同视角的输出应该优先落到哪个状态桶
- 明确这些方法论术语默认只在内部使用，不直接抛给最终用户

它不是：

- 数据库存储结构
- 后端 handler 的逐行脚本
- 必须和运行时代码一一同构的机械流程

### 9.2 rag-evidence-workflow

这个 skill 的定位是：

- 约束 source 何时可直入 项目知识库
- 约束何时必须先标准化
- 约束何时向 项目知识库 请求 grounded summary 和 citations
- 约束失败时如何回写状态

它与运行时的关系是：

- 提供工作流指导
- 帮助 prompt 和服务层保持一致
- 真实执行仍然由 `QdrantLlamaIndexEvidenceRuntime` 承担

### 9.3 项目内 RAG 与旧 skill 的边界

可以参考旧的 [PleasePrompto/rag-skill](https://github.com/PleasePrompto/rag-skill) 设计思路，但它不再是本项目的一期正式运行时。

### 9.4 artifact-generation-guidelines

这个 skill 的定位是：

- 约束何时应该把当前分析结果整理成交付物
- 约束 `document / page_solution / interaction_flow` 的类型选择
- 约束三类交付物的输出边界，避免跑偏

它默认由主 agent 在统一回合里自己参考，不由宿主先做关键词分流。

在本项目里，它的定位是：

- 参考 项目知识库 操作方式
- 参考 prompt 组织方式
- 参考历史 CLI 使用经验
- 作为迁移审查时的历史参考

它不是：

- 本项目唯一的正式 skill
- Claude 会自动从 `tools/` 或其他参考目录发现的项目级 skill
- 本项目运行时的 source of truth
- 可以直接代替 `EvidenceRuntime` 的东西

## 10. Source 接入与标准化

前台允许的输入类型：

- 文本粘贴
- PDF
- DOCX
- Markdown / Text
- 图片
- 音频
- XLSX
- URL
- YouTube URL
- 飞书纪要文本或导出文件

其中 项目知识库 直接能力边界按官方 source types 设计。超出其原生边界的输入，要先标准化。

一期明确这样处理：

- 文本 / PDF / DOCX / Markdown / Text / 图片 / 音频 / URL / YouTube：按可进入 项目知识库 的正式路径设计
- XLSX：先解析 sheet、表头、样例行、统计摘要，再生成 knowledge base-friendly 文本或 Markdown
- 飞书纪要：一期不做 OAuth 接入，只支持粘贴文本或上传导出文件

每个 source 入库后都至少要留下两类结果：

- 原始文件记录
- 标准化结果记录

## 11. 数据模型

一期核心对象如下：

### 11.1 Project

- `id`
- `name`
- `scenario_type`
- `summary`
- `status`
- `created_at`
- `updated_at`
- `seed_key`

### 11.2 Source

- `id`
- `project_id`
- `name`
- `source_kind`
- `upload_kind`
- `storage_path`
- `normalized_path`
- `knowledge base_import_mode`
- `parse_status`
- `parse_summary`
- `index_status`
- `sync_error`
- `created_at`

### 11.3 Message

- `id`
- `project_id`
- `role`
- `content`
- `source_refs_json`
- `created_at`
- `stream_group_id`

### 11.4 CurrentUnderstandingItem

- `id`
- `project_id`
- `category`
- `title`
- `body`
- `status`
- `source_ids_json`
- `updated_at`

### 11.5 ConflictItem

- `id`
- `project_id`
- `title`
- `body`
- `severity`
- `source_ids_json`
- `updated_at`

### 11.6 MvpItem

- `id`
- `project_id`
- `title`
- `body`
- `priority`
- `updated_at`

### 11.7 VersionSnapshot

- `id`
- `project_id`
- `trigger_kind`
- `summary`
- `state_json`
- `created_at`

### 11.8 KnowledgeBaseRecord

- `project_id`
- `provider`
- `knowledge_base_id`
- `index_status`
- `last_indexed_at`

### 11.9 DemoArtifact

- `id`
- `project_id`
- `artifact_type`
- `title`
- `summary`
- `status`
- `content_format`
- `storage_path`
- `metadata_json`
- `created_at`
- `updated_at`

阶段不再作为主存储对象。阶段只用于：

- 进度提示
- 版本快照触发语义
- artifact 形成时机

## 12. 聊天与状态推进

一期的聊天是项目分析链路，不是泛聊天框。

每轮对话的大致流程是：

1. 读取项目当前状态
2. 读取选中 source 和可用标准化结果
3. 向 项目知识库 请求 grounding
4. 将项目状态、最近消息和证据交给 Claude Agent SDK
5. 流式返回 assistant 输出
6. 同轮产出结构化 patch
7. patch 落库后通过 SSE 推给前端
8. 若命中关键条件，则生成版本快照或 artifact

每轮 assistant 的重点不是多说，而是推进。

一期默认每轮只做少量高价值推进，包括：

- 提问
- 当前理解
- 风险提醒
- scope 收敛
- artifact 触发

## 13. API 与 SSE

一期主 API：

- `POST /api/projects`
- `GET /api/projects`
- `GET /api/projects/{project_id}`
- `POST /api/projects/{project_id}/sources`
- `GET /api/projects/{project_id}/sources`
- `GET /api/projects/{project_id}/state`
- `POST /api/projects/{project_id}/chat/stream`
- `GET /api/projects/{project_id}/versions`
- `GET /api/projects/{project_id}/artifacts`
- `POST /api/projects/{project_id}/artifacts/generate`

`POST /api/projects/{project_id}/chat/stream` 请求体：

- `message`
- `selected_source_ids`
- `request_artifact_types`
- `client_context`

SSE 事件类型：

- `message_chunk`
- `citations`
- `current_understanding_patch`
- `pending_patch`
- `confirmed_patch`
- `conflict_patch`
- `mvp_patch`
- `artifact_patch`
- `version_patch`
- `done`
- `error`

所有 patch 事件统一带：

- `op`
- `items`
- `project_id`
- `event_id`
- `created_at`

## 14. 版本快照

版本快照自动生成，不让用户手工保存。

一期自动触发点：

- 初次完成 intake 摘要
- 初次形成业务理解摘要
- 初次形成真实需求定义
- 初次形成 MVP 方向
- artifact 生成成功

版本快照保存：

- 触发原因
- 摘要
- 当时的完整状态 JSON
- 关联消息范围

一期只做查看，不做回滚和 diff。

## 15. 交付物

一期交付物有三类：

- 文档稿
- 页面方案
- 交互稿

生成策略：

- 文档稿：模型生成结构化正文，落盘 JSON 和可渲染内容
- 页面方案：模型生成页面结构说明和 HTML 原型
- 交互稿：模型生成关键流程说明和 HTML 原型

展示策略：

- 文档稿：右侧抽屉
- 页面方案：大预览层
- 交互稿：大预览层

HTML artifact 需要最小校验：

- 有标题
- 有主体区块
- 有基本导航或信息结构
- 不依赖外链脚本
- 失败不覆盖上一个成功版本

## 16. 失败路径

失败路径按真实系统来处理，不靠静态 fallback 兜成“看起来没事”。

一期至少明确处理这些情况：

- Claude 未配置
- EvidenceRuntime 未配置
- 项目知识库索引失败
- 项目知识库检索失败
- artifact 生成失败
- SSE 中途断流
- source 标准化失败

处理原则：

- source 入库和 RAG 索引解耦
- 有失败就保留失败状态和错误信息
- 聊天可以在部分依赖失败时继续，但要如实说明证据能力不可用
- 不生成假的 citations

## 17. 验收方式

验收不写“测试通过”这种空话，一期按下面六类检查。

### 17.1 文档对齐检查

检查 `spec`、`todo`、`AGENTS.md`、项目级 skills 是否一致，是否还残留“旧半成品已经是基线”的说法。

### 17.2 Provider 真伪检查

检查：

- Claude 是否真实走 `Claude Agent SDK`
- 项目知识库 是否真实走 `Docling + Qdrant + LlamaIndex`
- 是否仍存在用本地 stub 冒充正式 provider 的命名和实现

### 17.3 UI 对齐检查

检查：

- 是否恢复到 `archive/legacy-demo` 级别的产品感
- 是否仍是三栏分析工作台
- 是否避免退化成后台配置页

### 17.4 失败路径检查

检查未配置、失败、断流、无证据等场景下，系统是否诚实暴露状态，而不是偷偷 fallback。

### 17.5 Chrome DevTools 联调检查

用 Chrome DevTools 实测：

- 首屏加载
- 资料上传
- 聊天滚动
- SSE 事件
- 右栏 patch 更新
- artifact 预览
- 控制台报错

### 17.6 专项 review

必要时交给其他 AI 做专项 review，至少覆盖：

- provider 真伪
- UI 对齐
- 失败路径
- 文档和实现一致性

## 18. 当前重做顺序

这份 spec 对应的实际推进顺序是：

1. 先改文档和规则
2. 再清理误导性的旧实现和命名
3. 再重建前端工作台
4. 再接真实 provider
5. 最后补验证和验收

在文档重新对齐之前，不把当前探索代码继续往前补。

## 19. 项目 wiki 综合层（phase-1.5）

phase-1 的 RAG 证据层（`Docling + Qdrant + LlamaIndex + EvidenceRuntime`）保持不动，phase-1.5 在它之上叠加一个**项目 wiki 综合层**。两者并存，分工不同。

### 19.1 定位

- **RAG = 证据层**：chunk 级 grounding；`confirmed_items` 与 artifact 的 `source_refs` 只来自 `query_project_evidence` 的真实返回。
- **Wiki = 综合层**：跨多份 source 合成的 markdown 页面（实体、术语、规则、冲突、待确认问题）。Wiki 由 LLM 维护，不是 Python 模板渲染。

### 19.2 实现要点

- 维护方式：异步 subagent，调用 `claude_agent_sdk.query()`，cwd 锁定 `data/projects/<project_id>/wiki/`，allowed_tools = Read / Write / Edit / Glob，permission_mode = bypassPermissions。
- 触发点：source 入库成功后 fire-and-forget；version checkpoint 形成后 fire-and-forget。RAG 是真值源，wiki 失败不回滚 RAG。
- 聊天侧：仅暴露 `wiki_list_pages` / `wiki_read_page` 读工具；不给写工具。`update_project_state` 工具校验 `confirmed_items.source_ids` 必须命中真实 catalog source，wiki slug 不通过。
- Citation 纪律：wiki 段落不能写进前端 `source_refs`；wiki 页面 front-matter 必须挂 `source_ids`，回查走 RAG。
- Readiness：dir 不可写 → `error`；SDK 未配 → `degraded_readonly`（已有页面只读）；维护链路 + SDK 都就绪 → `ready`。`POST /wiki/maintain?probe=true` 触发健康探针，写 `wiki/.health` 并验证。

### 19.3 phase-1.5 不做

- 不让聊天 agent 直接写 wiki（phase 2 再考虑）。
- 不做 wiki 的 lint 工作流。
- Wiki tab 在前端只提供 `WikiPanel` 自包含组件，不默认嵌入工作台右栏；嵌入 phase-1.5+ 再做。
