# 客户需求转译台 全栈一期 Todo

## 1. 文档用途

这份 todo 只做三件事：

- 记录当前一期真实进度
- 明确还没完成的主线工作
- 作为 `spec / execution-plan / AGENTS` 的落地任务视图

配套文档：

- [全栈一期 Spec](../product/fullstack-phase1-spec.md)
- [evidence runtime 迁移执行方案](./evidence-runtime-rag-execution-plan.md)

## 2. 当前状态快照

当前一期的真实主基线已经变成：

- `frontend/`：项目列表 + 三栏工作台
- `backend/`：FastAPI + SQLite + SSE + Claude Agent SDK + evidence runtime
- `data/`：项目文件、artifact、本地 SQLite、Qdrant 等项目内运行数据

当前已确认的正式主路径：

- 主智能体：`Claude Agent SDK`
- 证据层：`Docling + Qdrant + LlamaIndex + 项目内 EvidenceRuntime`
- 项目知识载体：项目级 knowledge base，而不是 notebook binding

当前已明确退场的主路径语义：

- notebook binding
- notebook library
- create and bind notebook
- sync to notebook
- 把 NotebookLM 当成一期证据层正式主 provider

## 3. 已完成

### 3.1 文档和规则

- [x] `docs/planning/evidence-runtime-rag-execution-plan.md` 已定稿并作为迁移执行基线
- [x] `docs/product/fullstack-phase1-spec.md` 已切到 evidence runtime 主路径口径
- [x] `AGENTS.md` 已切到 knowledge base / evidence runtime 规则口径
- [x] 项目级方法论 skill 已建立并纳入后端运行时
- [x] `archive/legacy-demo/` 已收口为产品感和交互基线

### 3.2 前端主路径

- [x] 首页改成项目列表页
- [x] 工作台主路由切到 `/projects/:projectId/workbench`
- [x] 三栏结构已接通真实后端数据
- [x] 左栏 source 支持文本导入
- [x] 左栏 source 支持文件上传
- [x] 左栏 source 支持多文件上传
- [x] 左栏 source 支持删除
- [x] 左栏 source 支持重建索引
- [x] source 摘要改成悬浮浮卡
- [x] 中栏聊天支持流式输出和引用展示
- [x] 右栏沉淀总集已接通真实 state API
- [x] 页面方案 / 交互稿走大预览层
- [x] 工作台显式展示 evidence / knowledge base 语义

### 3.3 后端主路径

- [x] FastAPI 应用入口已建立
- [x] SQLite 初始化和 seed project 初始化已建立
- [x] 项目、source、state、version、artifact 基础路由已建立
- [x] `GET /api/health` 已建立
- [x] SSE 聊天主路由已建立
- [x] source 标准化、入库、落盘主路径已建立
- [x] `knowledge_bases` 与 `source_chunks` 已建立
- [x] 项目级 knowledge base 初始化 / 查询 API 已建立
- [x] evidence runtime query 已替换聊天主链路
- [x] `selected_source_ids` 已真实进入 retrieval filter
- [x] source 删除主链路已切到本地资料与 evidence cleanup
- [x] ghost vector 命中已在 query 层被过滤
- [x] URL source 未完成 normalized text 时不会伪装成可索引正文

### 3.4 旧路线退场进展

- [x] 后端主聊天链路已不再依赖 NotebookLM query
- [x] provider readiness / project readiness 已切到 evidence 语义
- [x] 后端启动主路径已不再强依赖 `NotebookLMService` 初始化
- [x] 旧 notebook binding / library / create-and-bind API 已退出主路由
- [x] legacy `synced` source 在 reindex 后会回归 `indexed` 语义
- [x] source 删除主链路不再触发 NotebookLM 写路径

## 4. 进行中

### 4.1 前端遗留语义清理

- [x] 把工作台里仍残留的“绑定知识库”对话框与按钮结构改成真实 knowledge base 操作语义
- [x] 去掉前端类型和测试里对 `notebook_binding / notebooklm` 兼容字段的主语义依赖
- [x] 清理 `binding_required`、`待绑定` 等 legacy 状态映射

### 4.2 Source 侧补强

- [x] URL 导入入口补齐到 UI
- [ ] source 标准化结果展示再做一轮可读性整理
- [ ] source 异常信息和入库错误信息继续收敛成统一文案
- [ ] source 上传后的局部 loading、错误、重试态继续细化

### 4.3 Artifact 主链路加固

- [ ] 优化 Claude 首 token 时间，让用户更早看到真实进度反馈
- [ ] 把“聊天流式输出”和“结构化沉淀 patch”继续拆开，避免互相阻塞
- [ ] artifact 成功和失败状态继续细化到右栏和大预览层
- [ ] artifact 生成成功后自动补版本快照

## 5. 下一批要完成

### 5.1 前端知识库语义收口

- [x] 工作台不再保留 notebook-style bind/create-and-bind 交互壳子
- [x] 项目知识库详情弹层改成真实 knowledge base 状态面板
- [ ] seed project 的 source 状态展示改成 normalize / index / cited 语义

### 5.2 状态沉淀和版本

- [ ] 收敛哪些轮次必须做结构化沉淀，哪些轮次只保留聊天输出
- [ ] 减少“每轮都写沉淀”带来的延迟
- [ ] 版本快照只保留关键节点自动生成
- [ ] 右栏版本区补齐时间、触发原因、摘要

### 5.3 UI 回到正确产品感

- [ ] 继续对齐 `archive/legacy-demo` 的产品感基线
- [ ] 继续压缩顶部栏高度，只保留有用信息
- [ ] 持续避免页面退化成后台表单页
- [ ] 把工作台的紧凑度、信息密度和可讲解性再收一轮

## 6. 验收清单

### 6.1 Provider 真伪与主链路

- [x] Claude 主路径已走 `claude-agent-sdk`
- [x] 聊天主链路已走 evidence runtime
- [x] 新项目无需 notebook bind 即可初始化 knowledge base
- [ ] 再做一轮真实环境 provider readiness 验收
- [ ] 再做一轮 artifact 真实链路验收

### 6.2 失败路径

- [x] evidence runtime 未就绪时已提前暴露
- [x] URL / 二进制 source 未完成标准化时不伪装成功
- [x] source 删除时 provider 清理失败不阻断本地删除
- [ ] 再做一轮端到端失败路径联调

### 6.3 UI 与文档

- [x] 前端不再暴露 notebook binding / notebook library / sync to notebook 语义
- [ ] `spec / todo / AGENTS / execution-plan` 复核无矛盾
- [ ] 用 Chrome DevTools 重跑首页、上传、聊天、artifact 预览全链路

## 7. 近期执行顺序

接下来默认按这个顺序继续推进：

1. 清理前端残留的 notebook binding 风格语义和交互
2. 补齐 URL 导入与 source 状态可读性
3. 继续压缩聊天首响应时间和 artifact 反馈
4. 收口版本快照与关键轮次沉淀
5. 做一轮完整联调与专项验收

## 8. 当前验收口径

后续不再只写“测试通过”，统一按下面几类分别验：

- [ ] 文档对齐检查
- [ ] provider 真伪检查
- [ ] UI 对齐检查
- [ ] 失败路径检查
- [ ] Chrome DevTools 联调检查
- [ ] 必要时的专项 review
