<!-- Thanks for contributing! Please fill this out so reviewers (human and Codex) can move fast. -->

## PR title convention

PR titles MUST start with exactly one of these prefixes. Do not mix multiple types
in a single title - pick the one that matches the PR's primary purpose.

- `feat:` new feature or capability
- `fix:` bug fix
- `chore:` tooling, deps, build, config (no business logic)
- `perf:` performance improvement (no behavior change)
- `refactor:` code restructuring (no new feature, no bug fix)
- `docs:` documentation only
- `style:` formatting/whitespace (no logic change)
- `test:` adding or updating tests

Format: `type: short description` — e.g. `feat: 增加用户微信登录功能`, `fix: 修复登录页面密码框无法输入的 bug`.

A CI check (`pr-title`) validates this automatically; a non-conforming title will fail.

- [ ] My PR title uses exactly one prefix above and matches the PR's primary purpose

## What & why

<!-- What does this PR change, and why? Link related issues with "Closes #123". -->

## How verified

<!-- Commands you ran and what you observed. -->

- [ ] `cd backend && pytest` passes
- [ ] `cd frontend && npm run test` passes
- [ ] `cd frontend && npm run build` passes

## Engineering contract (see AGENTS.md)

- [ ] No fake/stub provider named like a real one; no silent fallback
- [ ] Failures/unconfigured states are surfaced explicitly
- [ ] RAG (evidence) vs LLM Wiki (synthesis) boundary respected
- [ ] No secrets committed

## Notes for reviewers

<!-- Anything reviewers should focus on, trade-offs, follow-ups. -->
