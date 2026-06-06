# Harness Run Contract

Date: 2026-04-30
Updated: 2026-06-02
Status: Active baseline for the Codex-led multi-agent harness

## Purpose

The Harness Run Contract is the stable per-run boundary between the local Codex
supervisor and any downstream implementation or assist channel. It prevents
CodexSDK, Codex CLI, Cursor, ChatGPT Web, Claude Code, OpenCode, ACP, CLI, and
Cloud API details from leaking into task payloads as uncontrolled state.

The local Codex supervisor owns delivery control. Executors and assist channels
produce candidate artifacts, logs, and receipts.

```text
User request
  -> local Codex supervisor
  -> Harness Run Contract
  -> provider adapter or assist channel
  -> artifacts + logs + verification evidence
  -> local supervisor gate
  -> accepted delivery or rework / blocked receipt
```

## Contract Files

- Canonical schema: `schemas/executor_run_contract.schema.json`
- Local validator: `tools/validate_executor_contract.py`

## Core Objects

### RunRequest

`RunRequest` describes what the supervisor wants done. It must be
provider-neutral.

Required fields:

- `task_id`
- `run_id`
- `idempotency_key`
- `executor.kind`
- `executor.model_hint`
- `executor.capability_requirements`
- `workspace.workdir`
- `workspace.worktree_policy`
- `objective`
- `goal_state` when the supervisor wants long-running objective state synced to a capable executor thread
- `requirement_context.original_user_request` when subagents or assist channels need high-fidelity user intent
- `provider_selection` when provider choice is prompt-controlled
- `delegation_policy` when agents receive explicit scoped autonomy
- `scope.in_scope`
- `scope.out_of_scope`
- `scope.paths`
- `constraints.network`
- `constraints.write_policy`
- `constraints.secrets_policy`
- `constraints.approval_policy`
- `verification.required_levels`
- `verification.commands`
- `verification.acceptance_criteria`
- `artifacts.required`
- `artifacts.optional`


Optional provider-neutral extension containers:

- `requirement_context`: preserves the original user request, traceable
  requirement items, must-preserve notes, assumptions, open questions, and
  explicit user overrides. The raw request remains the source of intent for
  subagents after redaction.
- `goal_state`: records the long-running supervisor objective separately from
  the per-run `objective`. `sync_mode=codex_app_server_goal_if_available` lets a
  Codex SDK adapter mirror the goal through app-server `thread/goal/*` methods
  after a capability probe. If that probe is absent or fails, the harness keeps
  `goal_state` as local receipt state and prompt context.
- `provider_selection`: records prompt-controlled or fixed provider preference
  over concrete provider IDs such as `chatgpt_web_manual`, `codex_cli`,
  `cursor_sdk`, or `antigravity_manual_assist`. Prompt family names such as
  `chatgpt`, `codex`, `cursor`, and `antigravity` resolve through registry
  `family_defaults` before entering the contract. Registry status and authority
  still limit what the provider may do.
- `delegation_policy`: records the autonomy envelope: context sharing, allowed
  operations, human-confirmation requirements, and `supervisor_gate_required`.
  This field grants scoped execution freedom, not delivery authority.
- `workflow_context`: execution-plan context for downstream agents. It carries
  the original end-to-end request, a concise process summary, the current round,
  and drift guards. It lets agents understand the larger flow, but it cannot
  expand the unit objective, owned paths, expected artifacts, acceptance checks,
  or supervisor gate.

Allowed executor kinds:

- `codex_multi_agent_harness`
- `codex_gpt55_local`
- `cursor_acp_worker`
- `cursor_cli_worker`
- `cursor_cloud_agent`
- `antigravity_agent` remains a future registry provider, not a verified executor kind until adapter proof exists
- `claude_code_worker`
- `opencode_worker`
- `reviewer`
- `custom_executor`

### RunEvent

`RunEvent` is the append-only progress stream. It is not a natural-language log.

The important lifecycle events are:

- `run.accepted`
- `run.leased`
- `workspace.prepared`
- `agent.started`
- `artifact.created`
- `verification.started`
- `verification.completed`
- `run.executor_succeeded`
- `run.gate_passed`
- `run.rework_required`
- `run.delivery_failed`
- `run.delivered`

`run.executor_succeeded` never means delivered. It only means the executor
finished its own work.

### ArtifactManifest

`ArtifactManifest` lists produced files with stable metadata.

Each artifact must include:

- `name`
- `path`
- `type`
- `sha256`
- `producer`

The local supervisor should reject delivery if required artifacts are missing,
unreadable, or lack a digest.

### VerificationReceipt

`VerificationReceipt` records verification evidence.

Each check must include:

- `name`
- `level`
- `status`
- `command`
- `exit_code`

Verification levels:

- `R0`: requirement normalization
- `D0`: design and plan review
- `L0`: static, schema, lint, generated-drift checks
- `L1`: unit and module tests
- `L2`: contract and integration tests
- `L3`: system, scenario, E2E, or simulation tests
- `L4`: staging or pre-production verification
- `L5`: canary or gray release verification
- `L6`: production post-deploy verification
- `G0`: long-term asset governance review

Any skipped or blocked level must be represented explicitly as `skipped` or
`blocked`; it must not be omitted.

A `passed` receipt must contain at least one check. A delivered run must contain
only passed checks with successful exit codes. Partial or blocked verification
can be reported, but it cannot be represented as delivered.

### ReviewVerdict

`ReviewVerdict` makes independent review actionable without naming a specific
review product or governance layer.

Allowed statuses:

- `accepted`
- `rework_required`
- `blocked`
- `not_run`

The local supervisor must not deliver when review returns `rework_required` or
`blocked`.

### RunResult

`RunResult` is the executor-side handoff after work stops.

Required fields:

- `run_id`
- `status`
- `artifact_manifest`
- `verification_receipt`
- `gate_decision`

Delivery invariants:

- `status == delivered` requires `verification_receipt.status == passed`.
- `status == delivered` requires at least one verification check.
- `status == delivered` requires every verification check to be `passed` with
  `exit_code == 0`.
- `status == delivered` requires `gate_decision.status == passed`.
- `status == delivered` requires at least one artifact in `artifact_manifest`.
- `status == delivered` is invalid if `review_verdict.status` is
  `rework_required` or `blocked`.

## State Machine

```text
accepted
  -> leased
  -> workspace_prepared
  -> executing
  -> executor_succeeded
  -> verifying
  -> gate_passed
  -> delivered
```

Allowed failure exits:

- `blocked`
- `failed`
- `cancelled`
- `rework_required`
- `delivery_failed`

`run.delivered` requires a prior `run.gate_passed` event. A direct transition
from executor success to delivery is a contract violation.

## Provider Policy

`codex_multi_agent_harness` is the preferred local orchestration kind. It may
use CodexSDK, Codex CLI, current-session subagents, local scripts, tests, and
approved MCP/tools behind the contract.

Cursor adapter kinds remain valid only as future or blocked paths. Without real
Cursor account authentication, Cursor runs must not be reported as verified by
reusing Codex OpenAI-compatible configuration.

ChatGPT Web manual and ChatGPT App no-API flows are external assist channels.
They may submit candidate artifacts and read supervisor receipts, but they must
not emit `RunResult` directly.

## Implementation Boundary

This baseline intentionally keeps provider internals behind adapters. The
supervisor sees stable contracts, artifacts, logs, receipts, and gate decisions.

The local Codex supervisor should own:

- contract validation
- run state
- gate decisions
- artifact relay
- delivery status

Executor adapters should own:

- vendor CLI/API/ACP details
- local subagents
- executor-specific skills/hooks/MCP
- workspace commands
- raw logs
