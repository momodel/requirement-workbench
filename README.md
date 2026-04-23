# 客户需求转译台

这是“客户需求转译台”的全栈一期主工程。

主产品是一个面向需求分析的三栏工作台：

- 左栏 `Sources`：项目知识库，负责资料导入、解析、同步、引用
- 中栏 `Chat`：用户和主智能体的需求分析对话，支持流式输出和引用依据
- 右栏 `Project State`：沉淀总集，聚合理解项、待确认项、冲突、MVP、版本快照和交付物

默认自带一个 `业财逐笔对账` seed project，方便直接演示和回归。

当前仓库不是“前端 demo 壳”，而是一期主工程。旧的 demo 和 HTML 原型都已归档到 `archive/legacy-demo/`，只作为视觉、交互和文案参考基线。

## 当前能力

当前主链路已经接上的部分：

- 项目列表页和三栏工作台
- 真实 FastAPI + SQLite + 本地文件落盘
- source 文本导入、文件上传、多文件上传、删除、失败后重新索引
- 项目级 knowledge base 初始化、详情查询、provider readiness
- `Docling + Qdrant + LlamaIndex + 项目内薄适配层` 组成的 evidence runtime 主路径
- 真实 `Claude Agent SDK` Python 依赖和运行时接入
- SSE 聊天流
- assistant Markdown 渲染
- 右栏沉淀总集、版本快照、artifact 列表
- 文档稿抽屉预览
- 页面方案 / 交互稿 HTML 大预览层

还没有完全收口的部分，见：

- [一期规格](docs/product/fullstack-phase1-spec.md)
- [一期 Todo](docs/planning/fullstack-phase1-todo.md)

## 技术路线

- 前端：`React + Vite + TypeScript + Tailwind`
- 后端：`FastAPI`
- 存储：`SQLite + data/projects/`
- 主智能体：`Claude Agent SDK`
- 证据层：`Docling + Qdrant + LlamaIndex + 项目内 EvidenceRuntime 薄适配层`
- 项目级方法论：`backend/.claude/skills/requirement-analysis-methodology/`
- 历史 NotebookLM 迁移参考：`backend/.claude/skills/notebooklm-evidence-workflow/`

说明：

- `Claude Agent SDK` 和 evidence runtime 都走真实 provider，不允许静默 fallback 成本地假实现
- 失败就报失败，未配置就报未配置
- `archive/legacy-demo/` 是新版 UI 和交互的参考基线，不是当前主路径代码

## 目录结构

```text
.
├── archive/
│   └── legacy-demo/                # 旧 demo、HTML 原型、历史文档归档
├── backend/
│   ├── .claude/skills/             # 后端运行时使用的项目级 skills
│   ├── app/                        # FastAPI 应用
│   ├── requirements.txt
│   └── .env.local.example
├── data/
│   ├── projects/                   # source / artifact 落盘
│   ├── qdrant/                     # 项目内向量索引数据（默认嵌入式 Qdrant）
│   └── sqlite/                     # SQLite 数据库
├── docs/
│   ├── product/
│   ├── planning/
│   └── demo/
└── frontend/
    ├── src/
    └── package.json
```

## 环境要求

- Python `3.11+`
- Node.js `18+`
- 一个可用的 `claude` CLI，或者在环境变量里显式配置 `CLAUDE_CODE_CLI_PATH`
- 首次安装依赖和配置 provider 时可正常联网

## 5 分钟启动

### 1. 准备后端环境

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 准备前端环境

```bash
cd frontend
npm install
```

### 3. 配置 Claude

后端会自动读取 `backend/.env.local`。

先复制示例文件：

```bash
cd backend
cp .env.local.example .env.local
```

然后填写最少这几个变量：

```bash
ANTHROPIC_API_KEY=你的key
ANTHROPIC_BASE_URL=https://coding.dashscope.aliyuncs.com/apps/anthropic
CLAUDE_MODEL=glm-5
```

按当前代码，Claude 运行还依赖一个可执行的 `claude` CLI：

- 如果 `claude` 已经在 `PATH` 里，后端会直接使用
- 如果不在 `PATH` 里，就在 `.env.local` 里补 `CLAUDE_CODE_CLI_PATH=/absolute/path/to/claude`

快速检查方式：

```bash
cd backend
source .venv/bin/activate
python -c "import claude_agent_sdk; print('claude_agent_sdk ok')"
which claude
```

如果 `which claude` 没输出，就需要配 `CLAUDE_CODE_CLI_PATH`。

### 4. 可选：调整 evidence runtime 配置

默认情况下，后端会使用项目内嵌入式 Qdrant 路径 `data/qdrant/`，不需要单独启动 Qdrant 服务。

如果你需要显式覆盖路径、远端 Qdrant 或查询参数，可以在 `backend/.env.local` 里补这些变量：

```bash
REQUIREMENT_WORKBENCH_QDRANT_PATH=../data/qdrant
# REQUIREMENT_WORKBENCH_QDRANT_URL=http://127.0.0.1:6333
# REQUIREMENT_WORKBENCH_QDRANT_COLLECTION_PREFIX=project
# REQUIREMENT_WORKBENCH_EVIDENCE_BACKEND=qdrant_llamaindex
# REQUIREMENT_WORKBENCH_EMBEDDER_BACKEND=fastembed
# EVIDENCE_QUERY_TIMEOUT_SECONDS=15
# EVIDENCE_TOP_K=6
```

### 5. 启动后端

```bash
cd backend
source .venv/bin/activate
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 9300 --reload
```

后端启动后会自动：

- 初始化 SQLite
- 初始化项目内数据目录
- 确保 seed project 存在
- 在首次需要时创建本地 Qdrant 数据目录

### 6. 启动前端

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 4173
```

打开：

- 前端工作台：[http://127.0.0.1:4173](http://127.0.0.1:4173)
- 后端健康检查：[http://127.0.0.1:9300/api/health](http://127.0.0.1:9300/api/health)

## 首次进入后怎么验证

建议按这条顺序快速验一遍：

1. 打开首页，确认项目列表能正常加载
2. 看首页或工作台的 provider readiness，确认 `Claude` 和 `Evidence` 不是未配置状态
3. 进入 seed project 的工作台，确认三栏都能显示
4. 如果新项目提示 `knowledge_base_missing`，先在工作台初始化项目知识库
5. 在左栏导入一段文本资料，确认 source 状态会进入 `indexing / indexed` 或给出明确失败原因
6. 发一条消息，确认中栏能收到 SSE 流式输出，右栏会逐步更新
7. 打开右栏 artifact，确认文档稿能在抽屉看，HTML artifact 能在大预览层看

## 开发入口

常用代码入口：

- 前端项目页：`frontend/src/features/projects/ProjectsPage.tsx`
- 前端工作台：`frontend/src/features/workbench/WorkbenchPage.tsx`
- 前端 API：`frontend/src/lib/api.ts`
- 后端入口：`backend/app/main.py`
- 后端配置：`backend/app/config.py`
- 聊天 SSE 路由：`backend/app/routes/chat.py`
- Source 路由：`backend/app/routes/sources.py`

开发前建议先读：

- [docs/product/fullstack-phase1-spec.md](docs/product/fullstack-phase1-spec.md)
- [docs/planning/fullstack-phase1-todo.md](docs/planning/fullstack-phase1-todo.md)
- [docs/README.md](docs/README.md)

## 常见问题

### 1. `ModuleNotFoundError: No module named 'claude_agent_sdk'`

说明后端虚拟环境还没装依赖。

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. `未找到 Claude Code CLI`

说明 Python 包装好了，但 CLI 没找到。

处理方式：

- 让 `claude` 出现在 `PATH`
- 或在 `backend/.env.local` 配 `CLAUDE_CODE_CLI_PATH`

### 3. `Evidence Runtime 未就绪`

先分三类看：

- 后端依赖没装全：在 `backend/.venv` 里补装 `qdrant-client`、`llama-index-*`、`docling`
- `.env.local` 把 `REQUIREMENT_WORKBENCH_EVIDENCE_BACKEND` 改成了非 `qdrant_llamaindex`
- 你显式配置了远端 `REQUIREMENT_WORKBENCH_QDRANT_URL`，但当前地址不可达

### 4. 新项目显示 `knowledge_base_missing`

这表示项目存在，但还没初始化自己的 knowledge base。

处理方式：

- 在工作台里点击初始化 knowledge base
- 或调用 `POST /api/projects/{project_id}/knowledge-base/init`

### 5. 某个 source 变成 `index_failed`

这表示 source 已标准化，但写入项目知识库失败。

当前 UI 已支持在 source 卡片上重新索引。重试前先确认：

- provider readiness 里的 `Evidence` 已就绪
- 该 source 的标准化结果已生成
- `data/qdrant/` 或显式配置的 `REQUIREMENT_WORKBENCH_QDRANT_URL` 可正常访问

## 归档和参考资产

这些内容不再作为主路径实现，但仍然有参考价值：

- 视觉和交互基线：[archive/legacy-demo/](archive/legacy-demo/)
- 归档说明：[archive/legacy-demo/README.md](archive/legacy-demo/README.md)

后续如果新版 UI 退化到明显弱于归档基线，应优先按归档基线回补产品感，而不是继续堆接口。
