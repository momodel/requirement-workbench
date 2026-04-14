# 客户需求转译台 Demo 开发计划

## 1. 项目目标

本项目的目标不是做一个普通的 AI 聊天页，也不是只产出 PRD 的文档工具，而是做一个可演示的 `客户需求转译台` 工作台：

- 让客户愿意自然开口，不抗拒交流
- 让客户可以方便地丢入各种上下文
- 让智能体用强引导能力把需求逐步聊清楚
- 让系统不仅输出文档，还能输出 demo / 原型帮助理解
- 让整个过程沉淀为项目状态，而不是散落在聊天记录里

本次实现面向 hackathon demo，优先级是：`先跑通前后端闭环，再打磨 UI`。

## 2. 已确认产品方向

### 2.1 主演示场景

- 使用更通用的 `客户需求转译台` 场景
- 不再以早期的业财对账案例作为主叙事
- 历史 demo、PRD、原型仍保留作为参考资产

### 2.2 对话体验

- 中间聊天区需要更像 ChatGPT 的字字流出
- 外层风格更像顾问，温和引导，不做强审问感
- 内层逻辑结合之前确认的平台方法论，保持分析严谨和推进节奏

### 2.3 输入能力

第一版支持并优先考虑以下输入方式：

- 粘贴文本
- PDF
- DOCX
- 图片
- XLSX
- 音频
- 飞书纪要

第一版不优先做复杂飞书 API 集成，优先支持：

- 粘贴飞书纪要内容
- 上传飞书导出的文本 / 文档

### 2.4 输出能力

第一版输出不只包含文档，还应包含：

- 当前理解
- 待确认项
- 已确认项
- 冲突项
- MVP 草案
- demo / 原型产物

### 2.5 版本能力

第一版版本功能只保留：

- 当前版本
- 版本快照列表

明确不做：

- 复杂版本 diff 页面
- 版本对比工作台
- 回滚流程

## 3. 方法论如何落地到产品

本项目的方法论不是展示给客户看的理论页，而是平台内部的分析与推进机制。

### 3.1 内生方法论

- `BABOK`：作为需求抽取骨架，保证目标、角色、流程、系统、规则、约束、风险等维度不遗漏
- `JTBD`：用于判断客户的真实任务与真实诉求，识别表层要求和真实需求之间的差异
- `Event Storming`：用于还原业务流程骨架，识别事件、角色、动作、系统和异常点
- `需求基线 / 变更管理`：用于维护状态，跟踪已确认、待确认、冲突和版本

### 3.2 平台内生处理流程

每轮分析与聊天都按照以下流程推进：

1. `摄取`：接收自然语言、文档、表格、图片、音频和会议纪要等输入
2. `结构化`：抽取目标、角色、流程、系统、规则、约束和风险
3. `真实需求判断`：区分表层说法与真正想解决的问题
4. `业务流程还原`：重建现状流程与异常链路
5. `冲突与缺失检测`：识别口径冲突、版本冲突和关键缺失项
6. `关键追问`：只提出最影响推进的 3-5 个问题
7. `当前理解回显`：把当前理解、边界和待确认内容讲清楚
8. `版本化确认`：在每轮确认后沉淀为版本快照

### 3.3 用户感知

用户不需要知道内部用了什么方法论，但应该清晰感受到：

- 智能体接话自然
- 智能体会温和地追问关键问题
- 智能体不会一上来就给大方案
- 智能体会持续帮忙收敛，而不是让对话发散
- 智能体能把理解和 demo 同步整理出来

## 4. 最终技术栈

### 4.1 前端

- `React`
- `Vite`
- `TypeScript`
- `shadcn/ui`
- `Tailwind CSS`
- `Zustand`

### 4.2 后端

- `Python`
- `FastAPI`
- `SSE` 用于流式聊天

### 4.3 存储

- `SQLite`
- 本地文件目录

### 4.4 AI / 资料层

- `NotebookLM CLI`

### 4.5 第一版明确不做

- `Postgres`
- `pgvector`
- 重型 agent framework
- 复杂消息队列
- 多租户
- 复杂权限系统
- 完整飞书 API 深度集成

## 5. 产品与架构定位

本产品按 `project-first` 设计，不按 `chat-first` 或 `RAG-first` 设计。

### 5.1 主对象

主对象是：

- `Project`

而不是：

- `Conversation`
- `Notebook`

### 5.2 核心思想

- 聊天只是输入与推进通道
- 文档只是证据来源
- 真正长期维护的是项目状态

### 5.3 NotebookLM 的角色

`NotebookLM` 在本项目中的定位是：

- 资料理解引擎
- 证据问答层

它负责：

- 资料导入
- 基于资料问答
- 摘要与引用依据

它不负责：

- 项目状态管理
- 需求裁决
- 冲突状态机
- 版本管理

## 6. 目标产品形态

## 6.1 三栏工作台

### 左栏：上下文输入区

- 粘贴文本
- 上传资料
- 输入来源列表
- 资料解析状态
- 当前引用证据

### 中栏：主对话区

- ChatGPT 风格流式输出
- 顾问式温和引导
- 当前轮追问
- 分析状态提示

### 右栏：项目沉淀区

- 当前理解
- 待确认项
- 已确认项
- 冲突项
- MVP 草案
- 当前版本
- 版本快照列表

### 底部 / 抽屉：demo 产出区

- 页面结构稿
- 低保真 HTML 原型
- 关键流程 demo

## 7. 流式聊天设计

虽然前台体验要像 ChatGPT 的字字流出，但后端实现不能只是简单 token 流，而应是：

- `消息文本流`
- `项目状态 patch 流`

### 7.1 SSE 事件类型

建议定义以下事件：

- `message_chunk`
- `citations`
- `understanding_patch`
- `pending_patch`
- `confirmed_patch`
- `conflict_patch`
- `mvp_patch`
- `version_patch`
- `done`

### 7.2 用户体验目标

- 中间聊天区看到连续流式文本
- 右侧沉淀区在同一轮对话中同步更新
- 智能体的追问、回显和结论不是聊天结束后一次性跳出来，而是逐步形成

## 8. 多模态输入处理策略

### 8.1 统一接入

所有输入先统一进入 `Source Ingestion` 管线，再根据类型走不同处理。

### 8.2 文件处理原则

- 文本类：直接存储并转入 NotebookLM
- 图片类：先提取说明文本，再进入证据池
- XLSX：提取表头、sheet 名、样例行和结构说明，再转成可理解上下文
- 音频：先转写，再作为纪要文本进入后续流程
- 飞书纪要：第一版以粘贴文本或导出文件上传为主

### 8.3 第一版目标

第一版的关键不是做到最强解析，而是让用户真的能方便地把上下文丢进来，并且系统能顺利接住。

## 9. 输出与 demo 生成策略

本项目第一版输出分两类：

### 9.1 结构化项目结果

- 当前理解
- 待确认项
- 已确认项
- 冲突项
- MVP 草案
- 当前版本 / 版本快照

### 9.2 帮助理解的 demo 结果

- 页面结构稿
- 低保真 HTML 原型
- 关键流程 demo

### 9.3 第一版不做

- 高保真 UI 自动生成平台
- 复杂代码生成器
- 通用产品原型工厂

## 10. 第一版核心数据对象

- `Project`
- `Source`
- `Message`
- `CurrentUnderstanding`
- `ConfirmationItem`
- `ConflictItem`
- `MvpItem`
- `RequirementVersion`
- `NotebookBinding`
- `DemoArtifact`

## 11. SQLite 第一版表设计

- `projects`
- `sources`
- `messages`
- `current_understandings`
- `confirmation_items`
- `conflict_items`
- `mvp_items`
- `versions`
- `notebook_bindings`
- `demo_artifacts`

## 12. 第一版 API 范围

- `POST /api/projects`
- `GET /api/projects`
- `GET /api/projects/:id`
- `POST /api/projects/:id/sources`
- `GET /api/projects/:id/sources`
- `GET /api/projects/:id/state`
- `POST /api/projects/:id/chat/stream`
- `POST /api/projects/:id/confirmation-items/:itemId/confirm`
- `POST /api/projects/:id/confirmation-items/:itemId/reject`
- `POST /api/projects/:id/versions`
- `GET /api/projects/:id/versions`
- `POST /api/projects/:id/demo-artifacts/generate`
- `GET /api/projects/:id/demo-artifacts`

## 13. 分阶段开发计划

### Phase 1 - 仓库整理与工程基线

目标：把当前仓库整理成真正可开发的前后端 demo 工程。

工作内容：

- 保留 `docs/`、`prototypes/`、`deliverables/` 等资产目录
- 保留旧前端 demo 作为布局和交互参考
- 新建 `backend/`、`data/`、`uploads/` 等目录
- 收敛本地和远端 git 状态，保证后续提交顺畅

交付结果：

- 工程目录清晰
- 前后端都能独立启动

### Phase 2 - 前端工作台骨架

目标：用 `shadcn/ui + Tailwind` 重建三栏工作台。

工作内容：

- 引入 Tailwind 和 shadcn/ui
- 建立新的三栏布局
- 先用 mock 数据渲染：
  - SourcePanel
  - ChatPanel
  - CurrentUnderstandingCard
  - PendingItemsCard
  - ConfirmedItemsCard
  - ConflictItemsCard
  - MvpDraftCard
  - CurrentVersionCard
  - VersionSnapshotList

交付结果：

- 新前端骨架可用
- 旧 demo 不再承担主前端职责

### Phase 3 - 后端基础能力

目标：建立项目状态系统和资料上传能力。

工作内容：

- FastAPI 项目骨架
- SQLite schema 初始化
- 项目 API
- 资料上传 API
- 本地文件保存

交付结果：

- 项目可创建
- 资料可上传
- 状态可读取

### Phase 4 - 多模态输入管线

目标：让多种资料都能进入项目并完成基础标准化。

工作内容：

- 文本、PDF、DOCX、图片、XLSX、音频接入
- 飞书纪要文本接入
- 统一 Source Ingestion 管线
- 形成标准化上下文表示

交付结果：

- 用户能方便地把各类上下文丢进来

### Phase 5 - NotebookLM 接入

目标：打通资料理解引擎。

工作内容：

- `NotebookLMService`
- 每个项目绑定 `notebook_id`
- 实时导入 source
- persona 初始化
- ask 能力接通

交付结果：

- 真实资料进入 NotebookLM
- 可获得基于资料的回答与引用依据

### Phase 6 - 流式聊天

目标：实现像 ChatGPT 一样的流式对话体验，同时更新项目状态。

工作内容：

- 后端 SSE
- 前端流式渲染
- 右侧状态 patch 推送
- 引用信息同步返回

交付结果：

- 中间聊天像 ChatGPT
- 右侧沉淀同步更新

### Phase 7 - 方法论落地成分析 pipeline

目标：让智能体具备强引导能力，并且这种能力建立在之前确认的方法论上。

工作内容：

- 基于平台流程实现：
  - 摄取
  - 结构化
  - 真实需求判断
  - 业务流程还原
  - 冲突与缺失检测
  - 关键追问
  - 当前理解回显
  - 版本更新
- 控制每轮只追关键问题，不做无限追问

交付结果：

- 智能体具备温和但明确的推进能力
- 对话能真正推动需求收敛

### Phase 8 - 版本快照

目标：让需求确认结果形成简单但可见的版本感。

工作内容：

- 当前版本展示
- 版本快照列表
- 版本摘要生成

交付结果：

- 用户可看到当前版本和历史快照

### Phase 9 - demo 产出能力

目标：让系统不只产出文档，也能产出便于理解的 demo。

工作内容：

- 页面结构稿生成
- HTML 低保真原型生成
- 关键流程 demo 产出

交付结果：

- 客户可通过 demo 快速理解方案

### Phase 10 - 演示打磨

目标：把整个链路打磨成可稳定演示的 hackathon demo。

工作内容：

- 固化 seed data
- 固化演示话术
- 优化 loading / empty / error 状态
- 准备 fallback 流程，避免现场故障

交付结果：

- 现场可稳定演示完整闭环

## 14. 验收标准

第一版 demo 的最低验收标准：

- 能创建一个 `客户需求转译台` 项目
- 能上传至少一种真实资料并成功进入 NotebookLM
- 能发起一次流式聊天
- 聊天过程像 ChatGPT 一样逐步输出
- 右侧至少同步更新：
  - 当前理解
  - 待确认项
  - 已确认项
  - 冲突项
  - MVP 草案
- 能保存当前版本并看到版本快照列表
- 能生成至少一个 demo artifact
- 整个链路前后端可演示跑通

## 15. 明确不做的内容

为了保证 hackathon 收敛，本次不做：

- Postgres / pgvector
- 复杂权限系统
- 多租户
- 复杂多人协同
- 复杂 diff 页面
- 工作流引擎平台化
- 大而全 agent 框架
- 高保真代码级产品生成
- 深度飞书 API 集成

## 16. 下一步执行建议

建议严格按以下顺序推进：

1. 先完成仓库整理和工程基线
2. 再完成前端三栏骨架
3. 再完成后端项目状态和上传能力
4. 再接入 NotebookLM
5. 再做 SSE 流式聊天
6. 再落分析 pipeline
7. 再补版本快照和 demo 生成
8. 最后做演示打磨

这样能保证项目始终围绕“闭环可演示”推进，而不是在中途被 UI、架构或大而全能力分散掉。
