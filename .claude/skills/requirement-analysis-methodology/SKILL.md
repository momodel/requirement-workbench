---
name: requirement-analysis-methodology
description: Use when analyzing customer requirements, reading project sources or chat transcripts, deciding what is understood versus pending or conflicting, planning clarification questions, or updating MVP and artifact direction for this project.
---

# Requirement Analysis Methodology

## Overview

This skill is the default working guide for the product's requirement-analysis brain. Use it when turning raw customer input, uploaded materials, and prior chat into structured project state.

It does not replace product runtime code. It tells the agent how to reason and what to extract before writing `current_understanding`, `pending_items`, `confirmed_items`, `conflict_items`, `mvp_items`, versions, or artifact requests.

## Core Workflow

1. Build context from the current `Project`, recent messages, selected sources, and existing project state.
2. Extract the stable analysis frame:
   - business goal
   - roles
   - process
   - systems and boundaries
   - rules, mappings, constraints, risks
3. Separate findings into:
   - already grounded
   - still missing
   - internally conflicting
4. Ask at most `3-5` high-value clarification questions for the current round.
5. Return a concise working view:
   - current understanding
   - pending confirmations
   - confirmed decisions
   - conflicts
   - MVP direction
6. Trigger versions and artifacts only when the discussion has crossed a meaningful checkpoint.

## Working Rules

- Prefer project-state updates over long freeform summaries.
- Do not dump methodology jargon to the user unless it genuinely helps.
- Treat customer wording and system wording as different layers. Translate between them instead of echoing both.
- Do not jump to solution mode before the scope, boundary, and rule conflicts are sufficiently clear.
- If evidence is weak, keep the item in `pending` or `conflict`; do not prematurely promote it to `confirmed`.

## State Decisions

- `current_understanding`
  - best current model of the problem, even if not fully confirmed
- `pending_items`
  - questions that block scope, rule, ownership, or acceptance decisions
- `confirmed_items`
  - facts or decisions explicitly grounded by user confirmation or reliable evidence
- `conflict_items`
  - contradictory rules, mismatched terms, mapping ambiguity, or version drift
- `mvp_items`
  - capabilities that survive after scope compression and risk review

Detailed category rules live in `references/state-taxonomy.md`.

## Clarification Strategy

Good questions usually target one of these:

- which business object is the real reconciliation anchor
- which system is the source of truth
- which exceptions need first-class handling
- what can be automated safely
- what must stay human-reviewed

Avoid low-value questions that merely restate the source material.

## Version And Artifact Triggers

Create or request a new version snapshot when the conversation crosses one of these checkpoints:

- first usable intake summary
- first business understanding summary
- first real requirement definition
- first stable MVP direction
- artifact generation success

Detailed output rules live in `references/artifact-rules.md`.

## References

Read these only when needed:

- `references/method-stack.md`
  - how `BABOK`, `JTBD`, and `Event Storming` contribute different lenses
- `references/state-taxonomy.md`
  - exact meaning of each state bucket
- `references/artifact-rules.md`
  - when to trigger versions, documents, page plans, and interaction drafts
