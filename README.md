# Requirement Workbench (客户需求转译台)

> Turn vague business asks into grounded, confirmed requirements.

Read this in [中文](README.zh-CN.md).

Requirement Workbench is a full-stack, AI-agent-driven workspace for requirements
analysis. Instead of being a generic chat wrapper, it pairs a Claude-Agent-SDK
analyst with a project-local RAG evidence layer, so every confirmed requirement and
deliverable is traceable back to the customer's own source material.

The product is organized as a three-pane workbench:

- **Left — Sources (项目知识库):** ingest, parse, index and cite project material
  (text, PDF, DOCX, XLSX, images, URLs, audio).
- **Center — Chat (需求分析对话):** a streaming conversation between the customer and
  the agent, where the agent actively interviews to clarify fuzzy needs and grounds
  its answers in retrieved evidence.
- **Right — Project State (沉淀总集):** the living synthesis — current understanding,
  pending items, conflicts, MVP scope, version snapshots, decision log and
  deliverables.

A `业财逐笔对账` (transaction-level financial reconciliation) seed project ships by
default for instant demo and regression.

## Why this exists

Customers struggle to articulate what they actually need, and traditional
back-and-forth leaves critical details unconfirmed. This project was hardened by
repeatedly hitting the walls of generic tools (NotebookLM, ChatGPT canvas) and
turning each lesson into a product capability: a custom RAG evidence layer, a
methodology-driven interview flow, domain-specific artifact types, and an
agent-led (not host-scripted) conversation.

## Architecture

| Layer            | Technology                                                        |
| ---------------- | ----------------------------------------------------------------- |
| Frontend         | React 18 · TypeScript · Vite · Tailwind CSS · Radix UI            |
| Backend          | FastAPI (Python 3.11+) · SSE streaming                            |
| Agent            | Claude Agent SDK                                                  |
| Evidence (RAG)   | Docling · Qdrant · LlamaIndex · FastEmbed (`bge-small-zh-v1.5`)   |
| Synthesis        | LLM Wiki (project-local markdown, maintained by a sub-agent)      |
| Storage          | SQLite (relational) · local filesystem · Qdrant (vectors)         |
| Audio (optional) | Aliyun FileTrans ASR · Qiniu object storage                       |

Design principle: providers (Claude Agent SDK, the RAG evidence layer) always run
against **real** backends — there is no silent fallback to local fakes. If something
is unconfigured or fails, it says so explicitly. See [AGENTS.md](AGENTS.md) for the
full engineering contract.

## Quick start

Prerequisites: Python `3.11+`, Node.js `18+`, network access, and a working `claude`
CLI (or `LLM_CLI_PATH` configured).

```bash
# 1. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.local.example .env.local   # then fill in LLM_API_KEY etc.

# 2. Start backend (from backend/, venv active)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 3. Frontend (separate shell)
cd frontend
npm install
npm run dev
```

- Workbench: http://127.0.0.1:5174
- Health check: http://127.0.0.1:8000/api/health

Minimum `backend/.env.local`:

```bash
LLM_API_KEY=your-key
LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/apps/anthropic
LLM_MODEL=glm-5
```

> First run downloads the embedding model `BAAI/bge-small-zh-v1.5` (~100 MB) and
> Docling parsing models on demand — the first ingest/question may take a few
> minutes. Optional audio (ASR + object storage) and RAG tuning variables are
> documented in [README.zh-CN.md](README.zh-CN.md) and `backend/.env.local.example`.

## Tests

```bash
# Backend
cd backend && source .venv/bin/activate && pytest

# Frontend
cd frontend && npm run test
```

## Repository layout

```text
backend/      FastAPI app, agent runtime, RAG evidence layer, tests
  app/        routes, services, config
  .claude/    backend CAS skills (methodology, RAG, artifacts, wiki)
frontend/     React + Vite workbench (features/projects, features/workbench)
docs/         product spec and planning notes
reports/      RAG optimization benchmarks and eval datasets
archive/      legacy demo + HTML prototypes (visual/interaction baseline only)
```

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md),
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and the security policy in
[SECURITY.md](SECURITY.md). Roadmap and direction live in [ROADMAP.md](ROADMAP.md).

This project uses **OpenAI Codex** in its maintenance workflow (automated PR review
and release automation); see [AGENTS.md](AGENTS.md) and `.github/workflows/`.

## License

[Apache License 2.0](LICENSE).
