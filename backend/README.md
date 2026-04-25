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
- 项目内 `Docling + Qdrant + LlamaIndex + EvidenceRuntime` 证据链路
- 后端 CAS 全局规则在 `backend/CLAUDE.md`
- 后端 CAS skills 在 `backend/.claude/skills/`
- 项目级 knowledge base 初始化与 readiness 接口
- source 自动标准化、切 chunk、写入 Qdrant，并在删除 source 时同步删除向量
- 已验证的项目知识库 RAG ingest / index / query / citations 链路

后续会按 `docs/planning/fullstack-phase1-todo.md` 继续补齐生产部署、观测和 artifact 落盘细节。
