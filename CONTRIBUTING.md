# Contributing to Requirement Workbench

Thanks for your interest in contributing! This document covers how to set up your
environment, the conventions we follow, and how to get a change merged.

Issues and pull requests are welcome in English or Chinese. Code comments and commit
messages should be in English; documentation can be either.

## Development setup

Prerequisites: Python `3.11+`, Node.js `18+`, a working `claude` CLI (or
`CLAUDE_CODE_CLI_PATH` configured), and network access for the Claude provider and
the RAG evidence layer.

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.local.example .env.local   # fill in at least ANTHROPIC_API_KEY

# Frontend
cd frontend
npm install
```

Run both as described in [README.md](README.md). The backend must be on port `8000`
before starting the frontend (Vite proxies `/api` to `127.0.0.1:8000`).

## Running tests

A change should keep both suites green:

```bash
cd backend && source .venv/bin/activate && pytest      # backend
cd frontend && npm run test                            # frontend (vitest)
cd frontend && npm run build                            # type-check + build
```

CI runs the same commands on every pull request (see `.github/workflows/ci.yml`).

## Engineering contract

This repo has a strict "no fake providers" rule. Before opening a PR, please read
[AGENTS.md](AGENTS.md). In short:

- Real providers only — no silent fallback to local fakes named like real services.
- If something is unconfigured or fails, surface it explicitly; never disguise a
  stub as "connected".
- The RAG layer is the **evidence** layer (chunk-level, line-traceable citations);
  the LLM Wiki is the **synthesis** layer. Don't blur the two.
- The backend host stays thin; business judgement belongs to the agent loop, not to
  host-side `if/else`.

## Pull request process

1. Fork and create a topic branch off `main`
   (e.g. `feat/...`, `fix/...`, `docs/...`).
2. Make your change with focused commits. Use clear, imperative commit messages.
3. Ensure tests, type-check and build pass locally.
4. Open a PR using the template; describe the change, the why, and how you verified
   it. Link any related issue.
5. PRs receive an automated review (we use OpenAI Codex in CI) plus human review.
   Address feedback and keep the branch up to date with `main`.

## Reporting bugs and proposing features

- Use the issue templates under `.github/ISSUE_TEMPLATE/`.
- For security issues, **do not** open a public issue — follow [SECURITY.md](SECURITY.md).

## Code of Conduct

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).
