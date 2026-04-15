---
name: notebooklm-evidence-workflow
description: Use when working with NotebookLM source ingestion, source normalization boundaries, grounded summaries, citations, or evidence retrieval for this project, especially when deciding whether a source can enter NotebookLM directly or must be normalized first.
---

# NotebookLM Evidence Workflow

## Overview

This skill defines how NotebookLM should be used inside this project. It is a workflow skill, not the runtime implementation itself.

Use it when deciding:

- whether a source can go directly into NotebookLM
- how unsupported inputs should be normalized
- when to query NotebookLM for grounding
- how to return summaries and citations to project state
- how to degrade when NotebookLM is unavailable

## Core Workflow

1. Classify the source type.
2. Decide whether NotebookLM can consume it directly.
3. If not, create a normalized text or markdown representation first.
4. Import or sync the normalized source.
5. Query NotebookLM only for evidence tasks:
   - grounded summary
   - source-backed clarification
   - citation extraction
6. Return results to the runtime in structured form.
7. If NotebookLM fails, keep source ingestion alive and mark sync status clearly.

## Direct Versus Normalized Inputs

Direct-capable source families in this project's current design:

- pasted text
- PDF
- DOCX
- Markdown or text
- image
- audio
- web URL
- YouTube URL

Normalize first:

- `XLSX`
- 飞书纪要原始内容 if it is not already a supported export format
- any structured export whose value is in tables, headings, or metadata rather than raw prose

Detailed normalization rules live in `references/source-normalization.md`.

## Query Rules

Use NotebookLM when the agent needs evidence, not when it needs state judgment.

Good NotebookLM tasks:

- summarize what the sources say about a topic
- extract likely mappings or rule statements
- provide citations for a conclusion draft
- compare what two sources say about the same issue

Do not delegate these decisions to NotebookLM:

- what becomes `confirmed`
- how scope is finally drawn
- whether a conflict is acceptable
- whether an MVP item should ship

Those decisions stay in product runtime and requirement-analysis logic.

## Failure Rules

- source ingestion must not fail just because NotebookLM sync fails
- failed sync should be visible in source status
- agent replies should degrade gracefully:
  - say grounding is unavailable
  - continue with available local summaries
  - avoid pretending citations exist when they do not

## External Reference Boundary

The external project [`PleasePrompto/notebooklm-skill`](https://github.com/PleasePrompto/notebooklm-skill) is useful as a reference for prompts and browser-automation workflow, but it is not this project's formal runtime foundation.

Use it as:

- reference material
- prompt inspiration
- implementation comparison

Do not use it as:

- the only runtime path
- the source of truth for project state
- a replacement for `EvidenceRuntime` or `NotebookLMService`

The repository README explicitly describes it as a local Claude Code skill, and distinguishes it from the author's MCP server for broader tool compatibility. See `references/external-notes.md`.

## References

Read these only when needed:

- `references/source-normalization.md`
  - normalization rules for `XLSX`, 飞书纪要, and structured sources
- `references/query-patterns.md`
  - when to ask NotebookLM and what to ask for
- `references/external-notes.md`
  - notes about the external `PleasePrompto/notebooklm-skill` and why this project treats it as reference rather than runtime
