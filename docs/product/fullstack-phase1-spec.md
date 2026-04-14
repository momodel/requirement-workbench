# 客户需求转译台 全栈一期 Spec

## 1. Summary

这份文档锁定为 `全栈一期` 的正式规格，不再只是前端演示壳。

- 主产品叙事：`通用客户需求转译台`
- 默认 seed project / 演示案例：`业财逐笔对账`
- 当前仓库里的 React demo 保留，但已归档为参考资产
- 一期目标：补齐 `FastAPI + SQLite + SSE + Claude Agent SDK + NotebookLM` 的完整闭环

本期已经确认的关键判断如下：

- 主智能体：`Claude Agent SDK`
- 证据理解层：`NotebookLM`
- 本地启动：前后端分开启动
- 交付物生成：允许模型自由生成，但必须经过后端结构化约束、校验和落盘
- 版本管理：关键轮次自动生成快照
- 输入边界：以 NotebookLM 官方支持的 source types 为正式能力边界；超出其原生能力的输入，必须先做服务端标准化

关于 NotebookLM source types，一期按用户已确认的信息约束设计：官方帮助当前列出的 source types 包括粘贴文本、音频、图片、Word / Text / Markdown / PDF、Web URL、YouTube URL，以及 Google Docs / Slides / Sheets。基于这个边界，`XLSX` 和 `飞书纪要` 不能按“NotebookLM 本地原生直传”设计，必须通过服务端转换或导入桥接后再进入 notebook。参考：[Add or discover new sources for your notebook](https://support.google.com/notebooklm/answer/16215270?co=GENIE.Platform%3DDesktop&hl=en)

## 2. 产品形态与用户路径

### 2.1 顶层对象

- 顶层对象是 `Project`，不是 `Conversation`
- 首页展示项目列表与“创建项目”
- 默认附带一个 `业财逐笔对账` seed project

### 2.2 主工作台

主工作台延续三栏结构，但语义升级为真实项目状态工作台：

- 左栏 `Sources`
  - 上传、导入、解析状态、当前引用、失败重试
- 中栏 `Chat`
  - 用户消息、智能体流式输出、引用依据、关键追问、当前轮分析状态
- 右栏 `Project State`
  - 当前理解、待确认项、已确认项、冲突项、MVP 草案、自动生成版本快照、交付物入口

### 2.3 交付物查看策略

- `页面方案` 和 `交互稿` 的 HTML 预览继续用大预览层，不放进窄抽屉
- `文档稿` 留在右侧抽屉查看

## 3. 技术与服务分层

### 3.1 前端

- 前端技术栈继续使用 `React + Vite + TypeScript`
- 主前端工程落在 `frontend/`
- 旧 demo 前端保留在 `archive/legacy-demo/frontend-vite-demo/` 作为参考
- 若引入 `shadcn/ui + Tailwind + Zustand`，应以不打断新主工程演进为前提

### 3.2 后端

新增 `backend/`，采用 `FastAPI`，负责：

- 项目状态管理
- 资料入库
- SSE 流式聊天
- 版本快照
- 交付物生成
- artifact 文件落盘

### 3.3 存储

- `SQLite` 保存元数据和项目状态
- 本地目录保存上传源文件、标准化结果和生成的 artifact

### 3.4 智能体编排

- `Claude Agent SDK` 负责主对话推进
- 必须通过 `AgentRuntime` 接口抽象，不把 Claude 写死到业务层

### 3.5 证据理解层

- `NotebookLMService` 独立封装
- 只负责资料导入、基于资料问答、返回摘要和引用
- 不参与项目状态写入，不承担项目裁决

### 3.6 适配层要求

必须引入两个接口：

- `AgentRuntime`
- `EvidenceRuntime`

目的是保留后续替换 Claude 或 NotebookLM 的空间。

## 4. 目录与代码结构

### 4.1 主目录结构

- `frontend/`
- `backend/`
- `data/`
- `docs/`
- `archive/legacy-demo/`

### 4.2 后端新增目录

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
- `backend/app/services/notebooklm_service.py`
- `backend/app/services/source_ingestion.py`
- `backend/app/services/project_state.py`
- `backend/app/services/artifact_generation.py`
- `backend/app/services/seed_projects.py`

### 4.3 数据目录

- `data/sqlite/`
- `data/projects/<project-id>/sources/`
- `data/projects/<project-id>/artifacts/`

### 4.4 前端建议拆分

- `frontend/src/App.tsx`：只保留路由入口职责
- `frontend/src/features/workbench/`：三栏工作台与 SSE 状态订阅
- `frontend/src/features/projects/`：项目列表和新建项目
- `frontend/src/lib/api.ts`：REST + SSE client
- `frontend/src/lib/types.ts`：前后端共享接口镜像
- `archive/legacy-demo/frontend-vite-demo/src/demoData.ts`：作为旧 demo fallback 参考，不再是主数据源

## 5. 核心数据模型

### 5.1 Project

- `id`
- `name`
- `scenario_type`
- `summary`
- `status`
- `created_at`
- `updated_at`
- `seed_key`

### 5.2 Source

- `id`
- `project_id`
- `name`
- `source_kind`
- `upload_kind`
- `storage_path`
- `normalized_path`
- `notebook_import_mode`
- `parse_status`
- `parse_summary`
- `created_at`

### 5.3 Message

- `id`
- `project_id`
- `role`
- `content`
- `source_refs_json`
- `created_at`
- `stream_group_id`

### 5.4 CurrentUnderstandingItem

- `id`
- `project_id`
- `category`
- `title`
- `body`
- `status`
- `source_ids_json`
- `updated_at`

### 5.5 ConflictItem

- `id`
- `project_id`
- `title`
- `body`
- `severity`
- `source_ids_json`
- `updated_at`

### 5.6 MvpItem

- `id`
- `project_id`
- `title`
- `body`
- `priority`
- `updated_at`

### 5.7 VersionSnapshot

- `id`
- `project_id`
- `trigger_kind`
- `summary`
- `state_json`
- `created_at`

### 5.8 NotebookBinding

- `project_id`
- `notebook_id`
- `provider`
- `sync_status`
- `last_synced_at`

### 5.9 DemoArtifact

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

### 5.10 一期固定状态分类

一期状态分类锁定为：

- `current_understanding`
- `pending_items`
- `confirmed_items`
- `conflict_items`
- `mvp_items`
- `versions`
- `artifacts`

不要再保留“阶段页专属状态对象”。阶段只作为工作流进度和自动快照触发条件，不作为存储主键。

## 6. 输入接入规则

### 6.1 前台允许的输入类型

- 文本粘贴
- PDF
- DOCX
- 图片
- XLSX
- 音频
- 飞书纪要文本 / 导出文件

### 6.2 NotebookLM 正式接入边界

下列类型可以在服务端标准化后直接导入 NotebookLM：

- 文本
- PDF
- DOCX
- Markdown
- 图片
- 音频
- URL
- YouTube

### 6.3 特殊输入规则

#### XLSX

后端必须先解析：

- sheet 名
- 表头
- 样例行
- 行列统计
- 关键信息摘要

然后再生成 Markdown 或 text 摘要文件作为 notebook source。不要把 `.xlsx` 当成 NotebookLM 原生输入设计。

#### 飞书纪要

一期不做飞书 OAuth 与开放平台深集成，只支持：

- 直接粘贴纪要文本
- 上传飞书导出的 DOCX / PDF / Markdown / Text

#### Google Docs / Slides / Sheets

- 不做一期正式前台入口
- 若后续接入，可在 service 层预留接口
- 不列入第一批 UI 能力

### 6.4 Source 入库要求

每个 source 入库都要产出两份内容：

- 原始文件记录
- 标准化摘要记录

NotebookLM 同步失败不能阻塞 source 入库。前端必须能看到以下状态：

- `已入库`
- `待同步`
- `同步失败`
- `已同步`

## 7. 主智能体与对话规则

### 7.1 Claude Agent SDK 负责的事情

- 读取当前项目状态
- 读取最近消息与可用 source 摘要
- 决定当前轮追问、回显、结论、状态 patch 和 artifact 生成请求

它不直接操作 SQLite；所有写入都通过后端 `project_state` 服务完成。

### 7.2 NotebookLM 负责的事情

- 基于 source 集合返回 grounded summary
- 针对追问提供引用证据
- 输出 citation-ready 的 source refs

它不负责：

- 项目状态管理
- 需求裁决
- 冲突状态机
- 版本管理

### 7.3 一轮对话的标准流程

1. 读取当前项目与 source 状态
2. 从 NotebookLM 拉取相关 grounding
3. 用 Claude Agent SDK 生成本轮 assistant 输出
4. 同时生成结构化 patch：`current / pending / confirmed / conflict / mvp / artifact / version trigger`
5. 后端边流式发消息边写状态

### 7.4 追问约束

- 一轮对话最多只允许生成 `3-5` 个关键追问
- 不做发散式盘问
- assistant 必须优先产出结构化 patch，再决定是否触发 artifact 生成

## 8. API 与 SSE 接口

### 8.1 REST API

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

### 8.2 Chat Stream 请求体

`POST /api/projects/{project_id}/chat/stream` 请求体锁定为：

- `message`
- `selected_source_ids`
- `request_artifact_types`
- `client_context`

### 8.3 SSE 事件类型

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

### 8.4 Patch 事件公共结构

每个 `*_patch` 事件统一带：

- `op`: `upsert | replace | remove`
- `items`
- `project_id`
- `event_id`
- `created_at`

前端不自行推导 patch 语义，只按后端事件更新 store。

## 9. 版本快照策略

### 9.1 触发原则

版本快照自动生成，不要求用户手工点击保存。

### 9.2 一期自动触发条件

- 初次完成 intake 后
- 首次形成业务理解摘要后
- 首次形成真实需求定义后
- 首次形成 MVP 结论后
- 每次 artifact 生成成功后

### 9.3 快照内容

每个快照必须保存：

- 触发原因
- 该时刻完整状态 JSON
- 摘要说明
- 关联消息范围

### 9.4 前端展示边界

- 右栏显示“当前版本 + 历史快照列表”
- 一期允许查看快照摘要与时间点
- 不做版本回滚
- 不做复杂 diff 页面

## 10. 交付物生成策略

### 10.1 交付物类型

- `文档稿`：主模型生成结构化文档内容，保存为 JSON + 可渲染正文
- `页面方案`：主模型生成页面结构说明与 HTML 原型
- `交互稿`：主模型生成关键流程说明与 HTML 原型

### 10.2 一期生成策略

用户已明确要求“模型自由生成”，一期按真实模型生成实现，不改为模板主导。

### 10.3 三道约束

为了让演示稳定，生成流程必须加三道约束：

1. `prompt 约束`
   - 明确输出结构
   - 禁止外链资源
   - 禁止任意脚本依赖
2. `结果校验`
   - 检查 HTML 是否包含必须区域、标题、页面导航
   - 拒绝空壳输出
3. `落盘策略`
   - 成功 artifact 保存为 `data/projects/<project-id>/artifacts/<artifact-id>/index.html`
   - 失败不覆盖上一个成功版本

### 10.4 前端展示策略

- 文档稿：右侧抽屉
- HTML 原型：居中大预览层
- artifact 列表永远从右栏“页面方案 / 交付物”区进入

## 11. 前端行为规格

### 11.1 首页

- 首页展示项目列表 + “新建项目”
- 默认初始化一个 `业财逐笔对账` seed project

### 11.2 工作台路由

- 主路由建议锁定为 `/projects/:projectId/workbench`

### 11.3 左栏 Source Panel

- 支持上传、查看状态、筛选已引用 source
- 点击 source 打开右侧悬浮摘要卡
- 每次打开摘要卡都滚到顶部

### 11.4 中栏 Chat Panel

- 使用 SSE 流式显示 assistant 文本
- 保留引用芯片
- 展示“当前分析中 / 正在同步资料 / 正在生成交付物”等状态

### 11.5 右栏 State Panel

- 按 `当前理解 / 待确认 / 已确认 / 冲突 / MVP / 版本 / 交付物` 分区
- patch 到来时即时更新，不等整轮对话结束
- 页面方案与交互稿点击后打开大预览层

### 11.6 Mock 回退策略

当前前端会先保留 seed / fallback mock 作为开发回退，但主路径必须切到真实 API 驱动。

## 12. Assumptions / Defaults

- 一期是单用户、本地演示环境
- 不做登录、多租户、权限系统
- 前后端分开启动是正式要求，不额外承诺一键启动
- 主产品是通用转译台，业财对账只是默认演示案例
- NotebookLM 只做资料理解层，不做项目状态管理
- 主智能体首版使用 `Claude Agent SDK`，但服务层必须保留适配接口
- source 支持范围以 NotebookLM 官方 source types 为上限；`XLSX` 与 `飞书纪要` 需要先在服务端转换 / 规范化
- artifact 采用模型自由生成，但必须经过后端落盘与校验
- 自动版本快照只做新增与展示，不做 diff 或回滚
