# 客户需求转译台 全栈一期 Todo

## 1. 当前状态

当前主路径已经切成：

- `frontend/`：项目列表 + 三栏工作台
- `backend/`：FastAPI + SQLite + SSE + provider 接入
- `data/`：项目文件、artifact、LLM Wiki 数据

正式 provider 路线：

- 主智能体：`Claude Agent SDK`
- 知识库：`LLM Wiki`

本项目不再接 NotebookLM。

## 2. 已完成

- [x] 首页改成项目列表页
- [x] 工作台主路由切到 `/projects/:projectId/workbench`
- [x] 三栏结构接通真实后端数据
- [x] source 支持文本导入、文件上传、多文件上传、删除、失败重试
- [x] 中栏聊天支持回车发送、`Shift + Enter` 换行
- [x] assistant 内容支持 Markdown 渲染
- [x] 右栏沉淀总集接通真实 state API
- [x] artifact 预览层和文档抽屉已接通
- [x] FastAPI、SQLite、seed project、SSE 聊天主路由已建立
- [x] `claude-agent-sdk` 进入后端依赖
- [x] LLM Wiki 按项目落到 `data/projects/<project_id>/wiki/`
- [x] 聊天链路读取 LLM Wiki 上下文
- [x] readiness 返回 `claude` 和 `knowledge_wiki`
- [x] 前端移除项目 notebook 绑定、library、自动创建入口

## 3. 进行中

- [ ] 优化 Claude 首 token 时间
- [ ] 拆开“聊天流式输出”和“结构化沉淀 patch”
- [ ] 把“读取知识库 / 分析 / 写入沉淀”阶段状态前置到 UI
- [ ] 减少“发送问题后长时间停顿”的体感
- [ ] 继续把 LLM Wiki 更新从 source intake 扩展到阶段性理解、artifact 成功和冲突沉淀

## 4. 下一批

- [ ] URL 导入入口补齐到 UI
- [ ] source 标准化结果展示再做一轮可读性整理
- [ ] source 异常信息和同步错误信息收敛成统一文案
- [ ] artifact 生成成功后自动补版本快照
- [ ] 版本快照只保留关键节点
- [ ] 右栏版本区补齐时间、触发原因、摘要
- [ ] 继续对齐 `archive/legacy-demo/` 的产品感基线

## 5. 验收清单

- [ ] 检查 Claude 主路径是否全部真走 `claude-agent-sdk + claude CLI`
- [ ] 检查 source 是否写入 LLM Wiki
- [ ] 检查聊天是否读取 LLM Wiki 上下文
- [ ] 清理残留的误导性命名、注释和文档
- [ ] 未配置 Claude 时必须明确报错
- [ ] LLM Wiki 写入失败时必须明确报错
- [ ] artifact 生成失败时必须明确报错
- [ ] 不允许静默 fallback 成本地假成功
- [ ] Chrome DevTools 重跑首页、上传、聊天、artifact 预览全链路

## 6. 当前执行顺序

1. 收口 LLM Wiki 与 RAG/source catalog 的边界
2. 压缩聊天首响应时间
3. 收口 artifact 生成、校验和预览
4. 收口版本快照和关键轮次沉淀
5. 继续把 UI 拉回到 `archive/legacy-demo/` 的产品感基线
6. 跑完整联调和专项验收
