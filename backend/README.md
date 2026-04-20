# Backend

这里是一期开发中的 FastAPI 后端。

当前已经具备这些能力：

- 应用入口
- SQLite 初始化
- 可重建的 seed project
- 项目 / source / message / state / version / artifact 路由
- SSE 聊天基础链路
- 真实 `Claude Agent SDK` artifact 生成
- 真实失败路径与 HTML artifact 校验
- 项目内 `NOTEBOOKLM_HOME` + `notebooklm-py` 证据链路
- 后端运行时 Claude skills 在 `backend/.claude/skills/`
- 项目级 Notebook library / 绑定 / 创建并绑定接口
- source 自动同步到项目 NotebookLM notebook 的文本与文件主路径
- 已验证的真实 NotebookLM create / bind / sync / query 链路

后续会按 `docs/planning/fullstack-phase1-todo.md` 逐步补齐真实存储、NotebookLM、Claude Agent SDK 和 artifact 落盘。
