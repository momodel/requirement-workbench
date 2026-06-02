# Roadmap

Requirement Workbench is built and maintained as a long-term open-source project, not
a one-off demo. This roadmap describes where it is and where it is heading. Dates are
indicative and may shift.

## Where we are (Phase 1 — shipped)

- Three-pane workbench (Sources / Chat / Project State) on a real FastAPI + SQLite
  backend.
- Multi-format source ingestion (text, PDF, DOCX, XLSX, images, URLs, audio) with
  normalization, local Qdrant indexing, readiness reporting, and retry-on-failure.
- Claude-Agent-SDK runtime with SSE streaming chat, grounded citations from the
  project knowledge base, and interview-driven clarification.
- Project State synthesis: understanding/pending/conflict items, MVP scope, version
  snapshots, decision log, and deliverables with per-type version history.
- LLM Wiki synthesis layer maintained by a sub-agent.
- Audio pipeline: object storage upload → ASR → normalized text → indexing.
- RAG optimization with measured results (see `reports/rag_optimization.md`):
  Chinese embedding lifted hit@1 from 7% to 57% on real data; a reranker pushed
  hit@1 to ~100% on the evaluation set.

## Near term

- Harden and document the public developer experience (CI, contribution flow,
  English docs) — in progress.
- Artifact export formats (currently mostly in-app).
- Broader automated test coverage, especially on the frontend.
- Provider abstraction polish so the evidence/agent layers are easier to swap.

## Later

- Deployment and observability guidance for self-hosting.
- Real-time (streaming) audio interviews, building on the current async ASR path.
- Pluggable methodology packs beyond the current requirements-analysis skill set.

## How we maintain it

We use OpenAI Codex in the maintenance loop — automated pull-request review and
release automation — alongside human review. See [AGENTS.md](AGENTS.md) and
`.github/workflows/` for the concrete setup.

Have an idea or want to help? Open an issue or a discussion. See
[CONTRIBUTING.md](CONTRIBUTING.md).
