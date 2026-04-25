# 客户需求转译台 全栈一期 Spec

## 1. 产品定位

客户需求转译台是一个需求分析工作台，不是对账系统本体。

一期目标是把一个客户需求项目从资料接入、聊天澄清、结构化沉淀，到交付物草稿生成跑通。系统以 Project 为组织单元，资料、对话、状态、Wiki 和交付物都归属于项目。

## 2. 当前正式路线

- 主智能体：`Claude Agent SDK`
- 项目知识库：`LLM Wiki`
- 后端：FastAPI + SQLite + SSE
- 前端：项目列表 + 三栏工作台
- 数据目录：优先使用项目内 `data/`

本项目不再以 NotebookLM 作为 provider、证据层或运行时依赖。

## 3. 核心体验

用户进入项目后看到三栏工作台：

- 左栏：项目知识库资料，支持文本、文件导入、删除、失败重试
- 中栏：需求分析聊天，支持流式回复和阶段状态
- 右栏：沉淀总集，展示当前理解、待确认项、已确认项、冲突项、MVP、版本和交付物

首页是项目列表，不做营销落地页。产品感以 `archive/legacy-demo/` 为基线，不能退化成后台配置页。

## 4. Source 与 LLM Wiki

source 上传后必须：

1. 落盘到项目目录
2. 写入本地 catalog
3. 标准化出可读摘要
4. 更新 `data/projects/<project_id>/wiki/`

LLM Wiki 至少维护这些页面：

- `index.md`
- `log.md`
- `project-overview.md`
- `source-intake.md`
- `state-summary.md`
- `rules-and-conflicts.md`

source 状态使用 `indexed` 表示已纳入项目 Wiki 上下文。失败时必须写清失败原因，不做伪装成功。

## 5. 聊天链路

聊天链路读取：

- 用户当前消息
- 最近消息
- 项目 state
- 当前 source 摘要
- LLM Wiki 上下文

Claude Agent SDK 负责生成回答和结构化沉淀。后端通过 SSE 推送：

- `assistant_status`
- `message_chunk`
- state patch
- artifact patch
- `done`
- `error`

如果 Claude 未配置、不可调用或超时，必须明确报错。

## 6. Readiness

全局 readiness 返回：

- `claude`
- `knowledge_wiki`

项目 readiness 返回：

- `project_id`
- `claude`
- `knowledge_wiki`

前端只展示这两个 provider 状态。不要出现项目 notebook 绑定、library、认证态等入口。

## 7. Artifact

一期交付物包括：

- `document`
- `page_solution`
- `interaction_flow`

artifact 生成要走真实 Claude Agent SDK。失败必须落到 UI 和 API 响应里，不能 fallback 成本地假结果。

## 8. Skill 边界

后端运行时使用的 Claude skill 统一放在：

- `backend/.claude/skills/requirement-analysis-methodology/SKILL.md`
- `backend/.claude/skills/llm-wiki-knowledge-workflow/SKILL.md`

代码显式读取这些 skill，不依赖根目录 `.claude/` 自动扫描。

## 9. 禁止项

- 不把 stub 命名成正式 provider
- 不把本地拼接摘要伪装成 Claude Agent SDK 输出
- 不引入 NotebookLM 运行依赖、认证流程、项目绑定或 UI 入口
- 不把用户家目录里的现成状态当成项目能力
- 不静默 fallback 成“看起来成功”

## 10. 验收口径

收尾前至少检查：

- 文档、skill、代码路线一致
- `CLAUDE_MODEL` 已配置，Claude Agent SDK 可调用
- LLM Wiki 能写入项目目录并被聊天链路读取
- 未配置、provider 失败、source 失败都有明确提示
- 前端仍是分析工作台，不是配置表单页
- 后端测试、前端测试、前端 build 通过
