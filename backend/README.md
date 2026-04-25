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
- LLM Wiki 项目知识库，落盘到 `data/projects/<project_id>/wiki/`
- 后端运行时 Claude skills 在 `backend/.claude/skills/`
- source 入库后写入 LLM Wiki 上下文

当前主链路是：

1. source 标准化、落盘、登记到本地 catalog
2. LLM Wiki 维护项目级知识页和更新日志
3. 聊天时读取 Wiki 上下文，交给 Claude Agent SDK 组织回答和沉淀

这个项目不再以 NotebookLM 作为 provider 或运行时依赖。
