# Contributing to Requirement Workbench

Thanks for your interest in contributing! This document covers how to set up your
environment, the conventions we follow, and how to get a change merged.

Issues and pull requests are welcome in English or Chinese. Code comments and commit
messages should be in English; documentation can be either.

## Development setup

Prerequisites: Python `3.11+`, Node.js `18+`, and network access for the LLM provider and
the RAG evidence layer.

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.local.example .env.local   # fill in at least LLM_API_KEY

# Frontend
cd frontend
npm install
```

Run both as described in [README.md](README.md). The backend must be on port `8000`
before starting the frontend (Vite proxies `/api` to `127.0.0.1:8000`).

To enable the pre-push AI review hook:

```bash
git config core.hooksPath .githooks
```

## Running tests

A change should keep both suites green:

```bash
cd backend && source .venv/bin/activate && pytest      # backend
cd frontend && npm run test                            # frontend (vitest)
cd frontend && npm run build                            # type-check + build
```

CI runs the same commands on every pull request (see `.github/workflows/ci.yml`).

## Pull request process

1. Fork the repository and create a feature branch from `main`
   - Branch naming convention: `{type}/{short-description}`, e.g. `feat/provider-settings-dialog`
   - Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`
2. Make your changes, ensuring all tests pass and the pre-push hook passes
3. Open a pull request to `momodel/requirement-workbench:main`
4. Wait for review and address any feedback
5. A maintainer will merge your PR once it's approved

PR titles must follow the same prefix convention as commit messages; a CI check will
enforce this.

If you are reporting a bug or proposing a new feature, please use the issue templates
in `.github/ISSUE_TEMPLATE/`.

## Engineering contract

This repo has a strict "no fake providers" rule. Before opening a PR, please read
[AGENTS.md](AGENTS.md). In short:

- Real providers only — no silent fallback to local fakes named like real services.
- If something is unconfigured or fails, surface it explicitly; never disguise a
  stub as "connected".
- The RAG layer is the **evidence** layer (chunk-level, line-traceable citations);
  the LLM Wiki is the synthesis layer (cross-source glossary/rules/open questions).
  Never conflate the two.

## Commit message convention

We use the conventional commit style prefixes:

- `feat:` new or enhanced functionality
- `fix:` bug fixes
- `docs:` documentation-only changes
- `style:` formatting, whitespace, naming cleanups
- `refactor:` code restructuring without behavior change
- `perf:` performance improvements
- `test:` adding/improving tests
- `chore:` build/CI/dev tooling changes

The title should be <= 72 characters. PRs with multiple commits will be squashed
unless the commits are independently meaningful.

## Code of conduct and security

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

If you find a security vulnerability, please follow the disclosure instructions in
[SECURITY.md](SECURITY.md).
