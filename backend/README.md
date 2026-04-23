# Backend

这里是一期主工程的 FastAPI 后端，当前主链路已经切到项目内 evidence runtime。

当前能力：

- SQLite 初始化与项目内数据目录管理
- 可重建的 seed project
- 项目 / source / message / state / version / artifact 路由
- 项目级 knowledge base 初始化、查询与 readiness
- source 标准化、索引、重建索引、删除以及 chunk ledger 持久化
- `Docling + Qdrant + LlamaIndex + 项目内薄适配层` 组成的 evidence runtime
- SSE 聊天基础链路
- 真实 `Claude Agent SDK` artifact 生成
- 真实失败路径与 HTML artifact 校验
- 后端运行时 Claude skills 在 `backend/.claude/skills/`

当前约定：

- 默认使用项目内 `data/qdrant/` 作为嵌入式向量存储目录；如果配置 `REQUIREMENT_WORKBENCH_QDRANT_URL`，则切到远端 Qdrant
- 仅启动后端并不会自动让项目进入“可检索”状态；knowledge base 初始化完成且至少一条 source 已完成索引后，Evidence 检索才真正可用
- `CLAUDE_MODEL` 是 Claude runtime 的硬前置条件，缺失时 readiness 和执行入口都会拒绝继续
- 仍需按 `docs/planning/fullstack-phase1-todo.md` 继续完成真实环境 provider readiness 验收与收尾联调
