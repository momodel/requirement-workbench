<!-- Thanks for contributing! Please fill this out so reviewers (human and Codex) can move fast. -->

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
