# Codex Harness Tooling Inventory

Date: 2026-06-02
Status: Active inventory for `harness_agent_approve`

## Purpose

This file is the lightweight entrypoint for reusable tools, docs, prompts, and
verification commands in this workspace. Update it when a task adds a durable
harness asset or when an old asset is downgraded to historical context.

## Current Architecture

- Active baseline: `docs/codex-led-harness-architecture.md`
- Open-source ecosystem research:
  `docs/codex-led-harness-open-source-ecosystem-research-2026-06-02.md`
- Evaluation standards:
  `docs/harness-evaluation-standards-2026-06-02.md`
- Project-local installation:
  `docs/project-local-harness-installation.md`
- Run contract: `docs/executor-run-contract.md`
- Provider and assist-channel boundaries: `docs/protocol-boundaries.md`
- Codex SDK language decision: `docs/codex-sdk-language-decision.md`
- Capability profile: `docs/project-capability-profile.md`
- Prompt ownership: `prompt_groups/codex_harness/README.md`

The previous platform-specific prompt group is removed from the active
workspace. Do not recreate it as a default harness entrypoint.

## Skills

- `openai-docs`: Use for current OpenAI/Codex product and API facts.
- `superpowers:brainstorming`: Use before new architecture or feature design.
- `superpowers:writing-plans`: Use before multi-step implementation.
- `superpowers:test-driven-development`: Use before behavior-changing code.
- `superpowers:verification-before-completion`: Use before any completion claim.
- `architecture-patterns` / `architecture-decision-records`: Use for formal
  architecture decisions when the harness design changes.
- `python-testing-patterns`: Use when expanding validator or harness tests.

## Local Tools

- `rg` / `rg --files`: Primary file and text search.
- Codex bundled Python:
  `C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- `git`: Worktree state, diffs, and delivery gates.
- `node`: Use for JavaScript tooling or SDK probes when needed.

## Active Harness Tools

- `tools/validate_executor_contract.py`: Standard-library validator for
  `RunRequest`, `RunEvent`, `ArtifactManifest`, `VerificationReceipt`,
  `ReviewVerdict`, and `RunResult`.
- `configs/harness-provider-registry.json`: Provider and assist-channel
  capability registry for CodexSDK, Codex CLI, ChatGPT Web, and future Cursor
  adapters.
- `tools/validate_harness_provider_registry.py`: Validator that keeps assist
  channels from gaining delivery authority and keeps Cursor blocked until real
  Cursor authentication is available.
- `tools/validate_harness_alignment.py`: Validator that keeps removed legacy
  platform surfaces out of active harness files and path names.
- `configs/harness-evaluation-registry.json`: Public benchmark, eval
  framework, observability, and safety-standard registry for scoring harness
  behavior without enabling automatic repair.
- `tools/validate_harness_evaluation_registry.py`: Validator for evaluation
  registry shape, source URLs, delivery-authority policy, disabled repair
  policy, and required category coverage.
- `tools/package_harness.py`: Standard-library pack/install/verify tool for
  project-local harness installation under a target project's `.codex-harness/`
  directory. It writes no global Codex configuration.
- `schemas/executor_run_contract.schema.json`: JSON Schema for the same
  contract objects. The filename is legacy; the schema title is now
  `Harness Run Contract`.
- `tools/validate_chatgpt_web_manual_assist.py`: Validator for ChatGPT Web
  request, upload, response, and local supervisor receipt packets.
- `tools/chatgpt_web_harness.py`: Prepares scoped source bundles and Web-primary
  packets, imports Web artifacts, applies candidate patches, and writes local
  supervisor receipts.
- `tools/chatgpt_web_execution_dispatcher.py`: Validates
  `codex-execution-plan.json`, computes serial/parallel batches, and can run
  `manual` or `codex-cli` dispatch backends.
- `tools/chatgpt_web_artifact_importer.py`: Imports `ARTIFACT:` blocks and
  publishes only receipt-accepted artifacts.
- `tools/chatgpt_web_simprint_bridge.py`: Assists a user-operated ChatGPT Web
  session through local CDP. It must not store Web credentials or treat browser
  state as verification evidence.
- `tools/chatgpt_app_no_api_connector.py`: Restricted artifact inbox and receipt
  reader for ChatGPT App / MCP no-API flows.
- `tools/chatgpt_app_supervisor.py`: Local supervisor for no-API connector
  candidate artifacts.
- `tools/chatgpt_app_proxy.py`: Proxy environment helper for local ChatGPT or
  tunnel access; it does not store credentials.

## Provider Status

- `codex_sdk`: Preferred future real backend for local supervised execution,
  implemented only with the official Python `openai-codex` SDK. The inspected
  `openai-codex@0.1.0b3` beta package exposes typed generated goal requests,
  sync/async API classes, `cwd` thread options, collab-agent thread items, and
  a pinned Codex runtime dependency. The inspected TypeScript
  `@openai/codex-sdk@0.137.0` package is documented as an official SDK but is
  not selected because its public types do not expose goal requests or a
  comparable low-level app-server RPC surface. Use
  `tools/probe_codex_sdk_capabilities.py` before claiming local support.
  Current local state: `openai-codex@0.1.0b3` is installed in the bundled
  Python runtime, `@openai/codex-sdk` is not installed locally or globally, and
  `openai-codex-cli-bin` is still missing because the runtime wheel download was
  too slow. A copied Codex Desktop binary at `.tmp/codex-runtime/codex.exe`
  reports `codex-cli 0.136.0-alpha.2` and has been verified with the Python SDK
  app-server initialize path via `CodexConfig.codex_bin`.
- `codex_cli`: Current implemented backend for dispatch receipts.
- `chatgpt_web_manual`: Candidate-artifact assist only.
- `chatgpt_app_no_api`: Structured candidate-artifact inbox only.
- `cursor_sdk` / `cursor_cli`: Deferred. Without real Cursor authentication,
  support may only emit capability probes or blocked receipts. Do not treat
  Codex OpenAI-compatible configuration as Cursor execution evidence.

## Removed Legacy Surfaces

Previous platform-specific prompts, overlay scripts, remote audit tools, and
design docs are no longer active workspace assets. The current harness keeps
reusable principles in Codex-led docs, schemas, prompts, and validators instead
of preserving old platform entrypoints.

## Verification Entry Points

Primary source-workspace verification:

```powershell
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python -m unittest tests.test_executor_contract_tools tests.test_harness_package_tools
```

Useful focused checks:

```powershell
& $python tools\validate_executor_contract.py <payload.json>
& $python tools\validate_harness_provider_registry.py configs\harness-provider-registry.json
& $python tools\validate_harness_evaluation_registry.py configs\harness-evaluation-registry.json
& $python tools\validate_harness_alignment.py
& $python tools\validate_chatgpt_web_manual_assist.py <packet.json>
& $python tools\package_harness.py pack --source . --output-dir dist
& $python tools\package_harness.py verify --target <project-root>
```

For an installed target project, run from the target project root:

```powershell
& $python .codex-harness\tools\package_harness.py verify --target .
```

Before closing substantial work, also run a stale-reference audit over active
entrypoints:

```powershell
& $python tools\validate_harness_alignment.py
```

Expected result: no removed legacy platform surfaces in active harness files.

## Governance Rules

- Keep `AGENTS.md` short; put durable architecture here or in `docs/`.
- Promote repeated manual commands into scripts or validators.
- Keep external assist outputs in `.tmp/` until local receipts accept them.
- Update this file whenever active tools or verification entrypoints change.
