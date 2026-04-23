# 客户需求转译台 全栈一期 Spec

## 1. 文档定位

这份文档描述当前一期的正式产品与实现基线。

如果现有代码、旧文档、探索实现和本 spec 冲突，以本 spec 为准。

当前一期已经进入 `evidence runtime` 迁移阶段，因此本 spec 同时受下面文档约束：

- [`docs/planning/evidence-runtime-rag-execution-plan.md`](../planning/evidence-runtime-rag-execution-plan.md)
- [`docs/planning/fullstack-phase1-todo.md`](../planning/fullstack-phase1-todo.md)
- [`AGENTS.md`](../../AGENTS.md)

需要明确：

- `archive/legacy-demo/` 仍然是产品感和交互基线
- 现有 `frontend/`、`backend/` 中不符合本 spec 的探索代码，不自动视为正式实现
- 旧 `NotebookLM` 路线不再是一期主链路正式方案

## 2. 一期目标

一期要交付一个真实可跑的本地单用户 `客户需求转译台`。

系统应能稳定跑通这条主链路：

1. 创建或打开一个项目
2. 上传或导入文本、URL、文件资料
3. 资料先完成标准化，再进入项目级 knowledge base
4. 用户在三栏工作台内持续对话
5. 主智能体基于项目状态和检索到的证据推进分析
6. 右侧项目状态持续沉淀
7. 关键轮次自动生成版本快照
8. 用户可以触发文档稿、页面方案、交互稿生成
9. 页面方案和交互稿以可交互 HTML 预览

一期不做：

- 登录、多用户、权限系统
- 在线部署稳定性工程
- 回滚、diff、协作审批流
- 真实业务系统集成
- 真实财务执行引擎
- 手工 notebook binding / library 管理式产品流程

## 3. 成功标准

### 3.1 产品标准

- 工作台必须保持三栏分析台，不退化成后台表单页
- 中栏聊天区是主角，左栏资料和右栏状态围绕分析过程服务
- 新版前端至少恢复到 `archive/legacy-demo/` 的工作台水准
- 默认 seed project `业财逐笔对账` 能从模糊需求一路讲到交付物生成

### 3.2 技术标准

- 前端采用 `React + Vite + TypeScript + shadcn/ui + Tailwind`
- 后端采用 `FastAPI + SQLite + SSE`
- 主智能体走真实 `Claude Agent SDK`
- 证据层走 `Docling + Qdrant + LlamaIndex + 项目内 EvidenceRuntime 薄适配层`
- provider / CLI / 数据目录优先收口到项目内路径
- 不允许用 stub、mock 或 fallback 冒充正式 provider

### 3.3 运行标准

- 前后端分开启动
- 本地可稳定完成一个项目从资料接入到 artifact 生成的完整流程
- 新项目无需 notebook bind 即可初始化项目级 knowledge base 并进入主链路

### 3.4 诚实性标准

- 未配置就明确报未配置
- provider 失败就明确报失败
- 未完成标准化的 source 不伪装成“已可检索”
- 没有检索命中时明确说明当前无相关证据
- 不在 UI、注释、文档里把兼容层写成正式主方案

## 4. 产品形态

### 4.1 顶层对象

系统顶层对象是 `Project`，不是 `Conversation`。

首页展示：

- 项目列表
- 创建项目入口
- 默认 seed project：`集团业财逐笔对账需求分析`

### 4.2 主工作台

主路由固定为 `/projects/:projectId/workbench`。

工作台保持三栏：

- 左栏 `Sources`
- 中栏 `Chat`
- 右栏 `Project State`

布局原则：

- 顶部为轻量项目头和状态条
- 三栏主体固定在视口内
- 各栏内部独立滚动
- 中栏聊天区优先级最高
- 页面方案和交互稿使用大预览层，不塞进窄抽屉

### 4.3 左栏 Sources

左栏负责资料接入与证据状态，不是配置页。

应包含：

- source 列表
- 文本导入入口
- URL 导入入口
- 文件上传入口
- 标准化状态
- 入库 / 索引状态
- 已引用标记
- 当前选中 source 的摘要浮卡

状态语义必须使用中性知识库语义：

- `normalize_status`
- `normalize_summary`
- `index_status`
- `index_error`

不再把 `NotebookLM 同步状态`、`notebook binding`、`library` 作为正式 UI 语义。

### 4.4 中栏 Chat

中栏是主界面。

应包含：

- 用户消息
- assistant 流式输出
- 引用 source 芯片
- 当前轮分析状态
- artifact 生成状态

聊天体验要求：

- 历史消息可完整回看
- 新消息到来自动滚到底部
- 工作台体现逐轮推进、追问、修正、沉淀
- 证据失败时允许降级继续分析，但必须明确说明当前无 grounding / citations

### 4.5 右栏 Project State

固定分区：

- 当前理解
- 待确认项
- 已确认项
- 冲突项
- MVP
- 版本快照
- 交付物

要求：

- state patch 到来即时更新
- 文档稿在右侧抽屉查看
- 页面方案和交互稿进入大预览层
- 版本快照展示摘要和触发原因

## 5. 默认案例

默认 seed project 为 `集团业财逐笔对账需求分析`。

案例约束：

- 上游业务系统：订单系统或结算系统
- 财务侧：财务系统中与业务系统对应科目的金额
- 对账粒度：逐笔对账
- 核心冲突：业务字段到财务科目映射口径不一致

它同时作为：

- 默认演示主线
- seed data 样本
- provider 联调固定回归案例

## 6. 前端规格

### 6.1 技术栈

前端采用：

- `React`
- `Vite`
- `TypeScript`
- `Tailwind CSS`
- `shadcn/ui`

### 6.2 视觉与交互基线

直接对齐 `archive/legacy-demo/` 的产品感。

含义是：

- 可以重写样式和实现
- 但不能退化成配置台、表单页或管理后台
- 需要保留分析工作台的密度、节奏和可讲解性

### 6.3 前端主模块

前端主工程位于 `frontend/`。

建议模块边界：

- `frontend/src/features/projects/`
- `frontend/src/features/workbench/`
- `frontend/src/features/sources/`
- `frontend/src/features/chat/`
- `frontend/src/features/project-state/`
- `frontend/src/features/artifacts/`
- `frontend/src/lib/api/`
- `frontend/src/lib/types/`

## 7. 后端规格

### 7.1 技术栈

后端采用：

- `FastAPI`
- `SQLite`
- `Pydantic`
- `SSE`

### 7.2 主职责

后端负责：

- 项目数据管理
- source 标准化与落盘
- 项目级 knowledge base 初始化
- source chunk ledger 维护
- evidence query
- Claude 对话与状态沉淀
- artifact 生成
- provider readiness 暴露

### 7.3 主路由

一期主路由应覆盖：

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}/sources`
- `POST /api/projects/{project_id}/sources`
- `DELETE /api/projects/{project_id}/sources/{source_id}`
- `POST /api/projects/{project_id}/sources/{source_id}/reindex`
- `POST /api/projects/{project_id}/knowledge-base/init`
- `GET /api/projects/{project_id}/knowledge-base`
- `GET /api/providers/readiness`
- `GET /api/projects/{project_id}/readiness`
- `POST /api/projects/{project_id}/chat/stream`
- artifact / state / version 相关路由

一期主路由不再把下面这些接口当正式主路径：

- `GET /api/projects/{project_id}/notebook-binding`
- `GET /api/projects/{project_id}/notebook-library`
- `POST /api/projects/{project_id}/notebook-binding`
- `POST /api/projects/{project_id}/notebook-create-and-bind`

### 7.4 数据模型

`Source` 对外语义应采用中性字段：

- `index_input_mode`
- `normalize_status`
- `normalize_summary`
- `index_status`
- `index_error`

迁移期允许数据库层兼容旧字段：

- `notebook_import_mode`
- `parse_status`
- `parse_summary`
- `sync_status`
- `sync_error`

但前端和文档必须以中性语义为主。

同时维护：

- `knowledge_bases`
- `source_chunks`

分别用于：

- 项目级 knowledge base 状态
- source chunk ledger、索引状态、定位与追溯

## 8. Provider 与运行时边界

### 8.1 Claude Agent SDK

Claude 是一期正式主智能体。

要求：

- 真实调用 `Claude Agent SDK`
- 明确读取项目内 skill
- 未配置 `CLAUDE_MODEL` 或 CLI 不可用时明确报错

### 8.2 Evidence Runtime

一期正式证据链路是：

- 文本优先标准化
- 文件标准化默认走 `Docling`
- 向量索引走 `Qdrant + LlamaIndex`
- 项目级语义由本项目内 `EvidenceRuntime` 薄适配层统一暴露

要求：

- `selected_source_ids` 必须真实进入 retrieval filter
- citations 必须来自真实 retrieval hits
- 已删除 source 的 ghost vector 不能继续出现在查询结果里
- 未完成标准化的 URL / 二进制 source 不能被伪装成可索引文本

### 8.3 NotebookLM 的当前边界

`NotebookLM` 不再是一期主链路正式 provider。

当前仅允许：

- 旧数据迁移核对
- 兼容期只读校验
- 历史 skill / 证据流程方法参考

当前不允许：

- 把 notebook binding / library 作为正式产品主流程
- 把 NotebookLM 写路径继续接回主链路
- 用旧 NotebookLM 成功结果掩盖新 evidence runtime 失败

## 9. Skill 约束

### 9.1 requirement-analysis-methodology

用于：

- 需求 intake
- 结构化分析
- 澄清问题
- 状态沉淀
- MVP 收敛
- artifact 触发判断

### 9.2 notebooklm-evidence-workflow

该 skill 仍保留在仓库中，但当前定位是：

- 历史 evidence 工作流参考
- source 标准化与 grounded 证据流程的迁移核对
- 旧路线与新路线对照时的辅助规则

它不再定义一期主链路正式 runtime 契约。

## 10. 验收标准

### 10.1 架构验收

- 证据层正式架构已经落到 `Docling + Qdrant + LlamaIndex + 项目内薄适配层`
- 项目内层没有膨胀成新的厚重自研 RAG 平台
- `Claude Agent SDK` 仍是最终分析与 artifact 生成主体

### 10.2 主链路验收

- 新项目无需 notebook bind 即可使用项目级 knowledge base
- source 能完成 `normalize -> chunk -> embed -> index`
- 聊天 query 主链路来自 evidence runtime
- `selected_source_ids` 真实影响 retrieval 结果
- citations 来自真实 retrieval hits

### 10.3 失败路径验收

- Qdrant 不可用、embedding 未配置、normalization 失败、query 超时、未命中都能明确暴露
- 聊天在证据层失败时可以降级继续，但不能伪造 grounding / citations
- 删除 source 时 provider 清理失败不会阻断本地删除

### 10.4 产品语义验收

- 前端不再暴露 notebook binding / notebook library / sync to notebook 语义
- source 状态、重试动作、readiness 面板都切换到 normalize / index / knowledge base 语义
- UI 语义与后端真实运行时一致

### 10.5 文档验收

- `spec / todo / AGENTS / execution-plan` 四者一致
- 文档里不再把旧 NotebookLM 路线描述成正式主方案
