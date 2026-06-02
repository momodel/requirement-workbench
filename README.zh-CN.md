# 客户需求转译台

Read this in [English](README.md).

这是“客户需求转译台”的全栈一期主工程。

主产品是一个面向需求分析的三栏工作台：

- 左栏 `Sources`：项目知识库，负责资料导入、解析、索引、引用
- 中栏 `Chat`：用户和主智能体的需求分析对话，支持流式输出和引用依据
- 右栏 `Project State`：沉淀总集，聚合理解项、待确认项、冲突、MVP、版本快照和交付物

默认自带一个 `业财逐笔对账` seed project，方便直接演示和回归。

当前仓库不是“前端 demo 壳”，而是一期主工程。旧的 demo 和 HTML 原型都已归档到 `archive/legacy-demo/`，只作为视觉、交互和文案参考基线。

## 当前能力

当前主链路已经接上的部分：

- 项目列表页和三栏工作台
- 真实 FastAPI + SQLite + 本地文件落盘
- source 文本导入、文件上传、多文件上传、删除、失败后重试索引
- 项目级 knowledge base 的初始化、查看 readiness
- 真实 `Docling + Qdrant + LlamaIndex` 接入，Qdrant 本地数据默认保存在项目内 `data/qdrant/`
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
- 证据层：`项目知识库`，当前 provider 为 `Docling + Qdrant + LlamaIndex`
- 后端 CAS 全局规则：`backend/CLAUDE.md`
- 后端方法论 skill：`backend/.claude/skills/requirement-analysis-methodology/`
- 后端 RAG 证据工作流：`backend/.claude/skills/rag-evidence-workflow/`
- 后端交付物约束：`backend/.claude/skills/artifact-generation-guidelines/`

说明：

- `Claude Agent SDK` 和 `项目知识库` 都走真实 provider，不允许静默 fallback 成本地假实现
- 失败就报失败，未配置就报未配置
- `Claude Agent SDK` 在这个项目里以 `backend/` 作为 project cwd 运行，因此只读取 `backend/CLAUDE.md` 和 `backend/.claude/skills/**`
- `archive/legacy-demo/` 是新版 UI 和交互的参考基线，不是当前主路径代码

## 目录结构

```text
.
├── archive/
│   └── legacy-demo/                # 旧 demo、HTML 原型、历史文档归档
├── backend/
│   ├── .claude/
│   │   └── skills/                 # 后端 CAS skills，仅供 backend/ 作用域自动发现
│   ├── CLAUDE.md                   # 后端 CAS 全局规则
│   ├── app/                        # FastAPI 应用
│   ├── requirements.txt
│   └── .env.local.example
├── data/
│   ├── qdrant/                    # 项目内向量索引数据
│   ├── projects/                   # source / artifact 落盘
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
- 可正常联网，供 Claude provider 和 项目知识库 使用

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
- 没装过的话，可以用 `npm i -g @anthropic-ai/claude-code` 装一份

快速检查方式：

```bash
cd backend
source .venv/bin/activate
python -c "import claude_agent_sdk; print('claude_agent_sdk ok')"
which claude
```

如果 `which claude` 没输出，就需要配 `CLAUDE_CODE_CLI_PATH`。

### 4. 配置音频 ASR + 七牛（可选，仅音频上传需要）

如果当前要验证“音频上传 -> 七牛对象存储 -> 阿里云转写 -> normalized text -> 项目内索引”这条链路，还需要在 `backend/.env.local` 里补音频 provider 配置。

阿里云转写：

```bash
REQUIREMENT_WORKBENCH_ALIYUN_AK_ID=你的AccessKeyId
REQUIREMENT_WORKBENCH_ALIYUN_AK_SECRET=你的AccessKeySecret
REQUIREMENT_WORKBENCH_ALIYUN_APP_KEY=你的AppKey
REQUIREMENT_WORKBENCH_ALIYUN_FILETRANS_REGION=cn-shanghai
REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_BACKEND=aliyun_filetrans
REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_TIMEOUT_SECONDS=300
REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_POLL_INTERVAL_SECONDS=2
```

七牛对象存储：

```bash
REQUIREMENT_WORKBENCH_QINIU_ACCESS_KEY=你的QiniuAccessKey
REQUIREMENT_WORKBENCH_QINIU_SECRET_KEY=你的QiniuSecretKey
REQUIREMENT_WORKBENCH_QINIU_BUCKET=你的Bucket
REQUIREMENT_WORKBENCH_QINIU_DOMAIN=https://你的公开访问域名
REQUIREMENT_WORKBENCH_QINIU_KEY_PREFIX=audio
```

说明：

- 这部分只在“音频 source 正式链路”里需要，文本 / PDF / 图片 / XLSX / URL 不依赖它
- 当前实现不做静默 fallback；未配置时，音频 source 会明确返回 `not_configured` / `normalization_failed`
- 七牛 `Domain` 必须是阿里云 FileTrans 可访问的公开地址，否则转写任务无法读取音频文件

音频链路排障脚本放在 `backend/scripts/`：

```bash
cd backend
source .venv/bin/activate
python scripts/check_audio_pipeline_config.py
python scripts/probe_audio_pipeline.py --url https://your-public-audio-url/test.mp3 --source-name test.mp3
```

### 5. 配置项目内 RAG

项目知识库不再依赖外部笔记本登录。默认使用本地 Qdrant 路径和 FastEmbed embedding。

可选配置写入 `backend/.env.local`：

```bash
REQUIREMENT_WORKBENCH_QDRANT_PATH=../data/qdrant
REQUIREMENT_WORKBENCH_EVIDENCE_BACKEND=qdrant_llamaindex
REQUIREMENT_WORKBENCH_EMBEDDER_BACKEND=fastembed
REQUIREMENT_WORKBENCH_EVIDENCE_QUERY_TIMEOUT_SECONDS=15
```

说明：

- Qdrant 本地索引默认保存在 `data/qdrant/`
- 上传 source 后会先落原文，再标准化、切 chunk、写入向量索引
- 缺依赖、embedding 初始化失败或 Qdrant 不可用时，readiness 会明确报错

### 6. 启动后端

```bash
cd backend
source .venv/bin/activate
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端启动后会自动：

- 初始化 SQLite
- 初始化数据目录
- 确保 seed project 存在

**首次启动注意**：第一次写入 source 或第一次发问题时，FastEmbed 会拉取 `BAAI/bge-small-zh-v1.5`（约 100MB），Docling 也会按需下载解析模型，整体可能要等几分钟。在此期间 readiness 显示就绪不代表索引就绪，看到日志确认模型下载完成再操作更稳。

### 7. 启动前端

```bash
cd frontend
npm run dev
```

Vite 默认起在 `5174`，并把 `/api` 反代到 `127.0.0.1:8000`，所以后端必须先按上一节起在 `8000`，否则前端所有请求都会 502。

打开：

- 前端工作台：[http://127.0.0.1:5174](http://127.0.0.1:5174)
- 后端健康检查：[http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

## 首次进入后怎么验证

建议按这条顺序快速验一遍：

1. 打开首页，确认项目列表能正常加载
2. 看首页或工作台的 provider readiness，确认 `Claude` 和 `项目知识库 RAG` 不是未配置状态
3. 进入 seed project 的工作台，确认三栏都能显示
4. 在左栏导入一段文本资料，确认 source 进入解析、索引并显示已索引
5. 发一条消息，确认中栏能收到 SSE 流式输出，右栏会逐步更新
6. 打开右栏 artifact，确认文档稿能在抽屉看，HTML artifact 能在大预览层看

如果是新项目，进入工作台后先初始化项目 knowledge base，再上传资料和提问。

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

### 3. `RAG provider 未配置或项目 knowledge base 未初始化`

先分三类看：

- 缺依赖：确认 `backend/requirements.txt` 已安装
- Qdrant 不可用：确认 `REQUIREMENT_WORKBENCH_QDRANT_PATH` 或 `REQUIREMENT_WORKBENCH_QDRANT_URL` 可用
- 项目未初始化：进入工作台后初始化项目 knowledge base

### 4. `项目知识库检索超时`

当前代码默认超时是 `30` 秒，可在 `backend/.env.local` 调整：

```bash
REQUIREMENT_WORKBENCH_EVIDENCE_QUERY_TIMEOUT_SECONDS=15
```

如果检索不稳定，优先确认：

- Qdrant 路径或服务是否可用
- embedding 模型是否初始化成功
- 当前项目是否已初始化 knowledge base
- 最近上传的资料是否已完成索引

### 6. 音频上传显示 `not_configured` 或 `normalization_failed`

先确认是不是音频 provider 没配齐。

当前音频主链路至少依赖：

- 七牛：`REQUIREMENT_WORKBENCH_QINIU_ACCESS_KEY`
- 七牛：`REQUIREMENT_WORKBENCH_QINIU_SECRET_KEY`
- 七牛：`REQUIREMENT_WORKBENCH_QINIU_BUCKET`
- 七牛：`REQUIREMENT_WORKBENCH_QINIU_DOMAIN`
- 阿里云：`REQUIREMENT_WORKBENCH_ALIYUN_AK_ID`
- 阿里云：`REQUIREMENT_WORKBENCH_ALIYUN_AK_SECRET`
- 阿里云：`REQUIREMENT_WORKBENCH_ALIYUN_APP_KEY`

如果这些变量缺失，当前实现会诚实报错，不会伪装成“正在处理中”。

### 5. 某个 source 变成 `index_failed`

这表示 source 已入库，但写入 RAG 索引失败。

当前 UI 已支持在 source 卡片上重试索引。重试前先确认：

- Qdrant 路径或服务可用
- embedding 模型可用
- 该 source 的标准化结果已生成

## 归档和参考资产

这些内容不再作为主路径实现，但仍然有参考价值：

- 视觉和交互基线：[archive/legacy-demo/](archive/legacy-demo/)
- 归档说明：[archive/legacy-demo/README.md](archive/legacy-demo/README.md)

后续如果新版 UI 退化到明显弱于归档基线，应优先按归档基线回补产品感，而不是继续堆接口。
