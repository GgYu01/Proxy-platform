# Project-Local Codex Harness Guide

This guide applies to the installed `.codex-harness/` directory in the current
project.

## Purpose

- This project has a project-local Codex-led multi-agent coding harness.
- The harness prepares scoped code context, analyzes requirements, designs
  serial/parallel work, dispatches candidate agents, verifies results, records
  receipts, and preserves reusable lessons.
- This installation is project-local. Do not treat it as a global Codex
  configuration.

## Read First

- `docs/codex-led-harness-architecture.md`
- `docs/codex-sdk-language-decision.md`
- `docs/project-local-harness-installation.md`
- `docs/codex_tooling_inventory.md`
- `docs/project-capability-profile.md`
- `docs/protocol-boundaries.md`
- `prompt_groups/codex_harness/README.md`

## Boundary Rules

- Local Codex supervisor is the delivery authority for this project.
- ChatGPT Web and ChatGPT App no-API flows are candidate-artifact assist
  channels; they are not local verification or delivery authorities.
- CodexSDK means the official Python `openai-codex` SDK adapter only; Codex CLI
  remains the fallback local execution backend.
- CursorSDK/Cursor CLI support requires real Cursor authentication. Without it,
  only capability probes or blocked receipts are valid.
- Provider-specific handles, session IDs, credentials, browser tokens, and
  product internals must stay out of run contracts and tracked assets.

## Verification

Run from the target project root:

```powershell
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python .codex-harness\tools\package_harness.py verify --target .
```
