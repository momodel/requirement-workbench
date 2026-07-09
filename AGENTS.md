# Repository Guidelines

> 中文版：[AGENTS.zh-CN.md](AGENTS.zh-CN.md)

This file is the working contract for both human contributors and coding agents
(including the OpenAI Codex review that runs in CI). Read it before making changes.

## Read first

For any implementation task, start with these three:

- `docs/product/fullstack-phase1-spec.md`
- `docs/planning/fullstack-phase1-todo.md`
- `archive/legacy-demo/README.md`

When the docs and the existing code disagree, the docs win.

For backend runtime rules, read:

- `backend/CLAUDE.md`
- `backend/.claude/skills/**/SKILL.md`

If your task touches one of these backend areas, also read the matching skill:

- `requirement-analysis-methodology` — requirements analysis flow, state synthesis,
  version snapshots, artifact triggering.
- `rag-evidence-workflow` — source ingestion, project knowledge-base indexing,
  grounding, citations.
- `llm-wiki-knowledge-workflow` — the LLM Wiki synthesis layer (entity pages, glossary,
  rules, conflicts, open questions), maintained by the WikiMaintainer sub-agent.
- `artifact-generation-guidelines` — the boundaries for generating document drafts,
  page plans, and interaction drafts.

These backend skills are reference material for the backend runtime. Their existence does not
mean a feature is wired up.

For project-level contributions, there is also:
- `.claude/skills/agentic-code-review` — automated local pre-push code review using
  the project's own LLM.

## Project baseline

- The repo already contains exploratory frontend and backend code. None of it is
  authoritative by default.
- Keep a piece of code only if it matches the current `spec` and `todo`.
- The product-feel and interaction baseline lives in `archive/legacy-demo/`.
- New work may rewrite styling and implementation, but must not regress into a
  back-office form or a settings page.

## Technical direction

- Agent: LangChain (Anthropic / OpenAI-protocol LLM).
- Evidence layer: `Docling + Qdrant + LlamaIndex` plus the in-repo `EvidenceRuntime`.
- Synthesis layer: the `LLM Wiki` (project-local markdown maintained by the
  WikiMaintainer sub-agent via a LangChain LLM).

Do not:

- stitch results together with local rules and call it `ClaudeAgentRuntime`;
- run a local summarizer and call it `EvidenceRuntime`;
- render markdown from Python templates and call it `LLMWikiService` / `WikiRuntime`;
- describe a stub as a "connected provider" in docs, comments, or the UI;
- silently fall back when something is unconfigured.

If it is unconfigured, say so. If it fails, report the failure.

### Wiki vs RAG boundary

- **RAG is the evidence layer:** chunk-level citations traceable to source line
  numbers. `confirmed_items` and artifact `source_refs` must come only from real
  `query_project_evidence` returns.
- **Wiki is the synthesis layer:** cross-source synthesis, glossary, rules, conflicts,
  open questions. Every assertion on a wiki page must carry `source_ids` in its front
  matter, and lookups still go through RAG to fetch the original text.
- Never pass a wiki paragraph to the frontend as a citation, and never let the wiki
  stand in for the evidence layer when RAG is unavailable.
- After a successful ingest, wiki maintenance is a fire-and-forget background task; a
  wiki failure does not roll back RAG.

## Dependency boundary

- Prefer in-repo runtimes, scripts, and data directories over whatever is installed in
  the developer's home directory.
- "It happens to be on my machine" is not a project capability.
- Confirm that providers, CLIs, skills, auth state, and data directories resolve to
  in-repo paths.
- If a step still requires manual login or authorization, call it out explicitly as
  the one thing a human must do.

## Backend CAS scope

- The backend service starts from `backend/` by default.
- The agent's project cwd is also fixed to `backend/`.
- `backend/CLAUDE.md` and `backend/.claude/**` serve the backend runtime only.
- The root-level project docs and dev rules are not the runtime prompt source.
- If any code, doc, or script still treats the runtime scope as the repo root, that is
  considered out of alignment.

## Development principles

### Host vs agent responsibilities

- The backend uses a thin host plus a single agent loop — no heavy `ChatService`
  orchestration.
- The host handles: HTTP / SSE, tool / MCP registration, persistence, timeouts and
  error handling, and event forwarding.
- The host must not make business judgements for the model, e.g.:
  - always querying the knowledge base before chatting;
  - guessing from keywords whether to write state;
  - re-inferring from assistant text whether to generate an artifact;
  - simulating the analysis flow with a long `if/else` chain.

### Skill / Tool / MCP principles

- A skill is long-lived methodology reference; it does not store the project's dynamic
  state.
- A tool is a real action the model can invoke, not an alias for host-side `if/else`.
- MCP is for external capabilities or capability surfaces worth reusing on their own —
  do not over-split.
- Do not duplicate the same large policy across `backend/CLAUDE.md`, the runtime
  prompt, a skill, and a tool description.

### Frontend/backend event principles

- The frontend shows real agent-loop events, not host-invented steps.
- `assistant_status`, tool running/completed, patch, artifact, and version events come
  from real run results.
- The right-hand state, versions, and deliverables are driven by real patches, not
  guessed from message text.

## Local environment

- Run Python commands through `backend/.venv/bin/...`.
- Run frontend commands from `frontend/`.
- Before running tests, starting services, or verifying endpoints, confirm the current
  worktree's local environment works.
- When a command fails, first distinguish: wrong path, environment not installed in
  this worktree, or a genuinely missing project dependency.

## Preflight

Before implementing or accepting work, run these checks:

1. Align with the docs: `docs/product/fullstack-phase1-spec.md`,
   `docs/planning/fullstack-phase1-todo.md`, `AGENTS.md`.
2. If the task touches the backend runtime, also align with `backend/CLAUDE.md` and the
   relevant backend skills.
3. Verify provider readiness first — do not build the feature and bolt on checks later.

You may not call the main path "wired up" unless all of these pass:

- A compatible LLM is callable.
- `LLM_MODEL` (legacy env name: `CLAUDE_MODEL`) is configured.
- The in-repo `Docling + Qdrant + LlamaIndex` provider is callable.
- The project knowledge base is authenticated.
- The current project has initialized its own knowledge base.
- The LLM Wiki maintenance path is callable: WikiMaintainer injected, LLM ready,
  and `POST /wiki/maintain?probe=true` can write and verify a marker in `wiki/.health`.

## Continuous checks

- A path existing, a class name looking real, or an interface shell starting up does
  not mean a provider is connected.
- Do not name a stub, mock, or fallback after a real provider.
- Do not treat ready-made state in your personal environment as a project capability.
- On the frontend, do not check only whether a feature works — also compare against
  `archive/legacy-demo/` to ensure the product feel has not regressed into a back-office
  form.
- For every main path you add, add the failure path too, not just the happy path.

## Acceptance

At minimum, check each of these when wrapping up:

- doc alignment;
- provider authenticity;
- UI alignment;
- failure paths;
- Chrome DevTools integration;
- a focused review where needed.

If preflight or a key acceptance item does not pass, do not package it as "basically
working".

## Default order of work

Unless the user changes the order, follow this:

1. Align docs and rules.
2. Remove misleading legacy implementations.
3. Rebuild the frontend workbench.
4. Wire up real providers.
5. Integrate and accept.
