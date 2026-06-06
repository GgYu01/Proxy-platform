# Executor Materialization Profile

Date: 2026-06-02
Status: Active Codex-led harness baseline

## Purpose

The Executor Materialization Profile defines how the project capability profile
is projected into concrete provider runtimes without changing the Harness Run
Contract.

The same harness run may use CodexSDK, Codex CLI, a future Cursor adapter,
Claude Code, OpenCode, or a human-operated ChatGPT Web assist channel. Their
local configuration formats differ, but the supervisor should still receive the
same run events, artifact manifests, verification receipts, and gate inputs.

## Materialization Matrix

| Capability | CodexSDK | Codex CLI | Cursor | ChatGPT Web |
|---|---|---|---|---|
| Stable repo guidance | `AGENTS.md`, docs, prompt group | same | adapter prompt/config | sanitized packet prompt |
| Repeatable workflow | SDK thread/run wrapper | `codex exec` dispatcher | future adapter | manual upload/download or connector inbox |
| External tools | SDK/tool config | local CLI/MCP/scripts | Cursor tools behind adapter | Web file analysis only |
| Subtasks | SDK threads or harness units | serial/parallel CLI units | future Cursor workers | `codex-execution-plan.json` proposal only |
| Security policy | sandbox/approval config | sandbox/approval config | Cursor auth and permissions | no secrets, no local authority |
| Output handoff | contract JSON + artifacts | contract JSON + artifacts | blocked/probed until authenticated | candidate artifacts + local receipt |

## Codex Default Profile

Codex is the default first-class executor for this baseline.

Recommended materialization:

```yaml
codex_multi_agent_harness:
  model_hint: gpt-5.5
  reasoning_effort: high
  project_guidance:
    - AGENTS.md
    - docs/codex-led-harness-architecture.md
    - docs/executor-run-contract.md
    - docs/protocol-boundaries.md
  skills:
    - verification-before-completion
    - openai-docs
  runtime:
    sandbox: workspace-write
    approval_policy: auto
    network: mirror-first
  dispatch:
    graph: serial_or_parallel_batches
    required_unit_fields:
      - id
      - title
      - dispatch_mode
      - owned_paths
      - depends_on
      - expected_artifacts
  output:
    required:
      - artifact_manifest
      - verification_receipt
      - run_result_or_blocked_receipt
```

Codex may use subagents internally, but it must not expose subagent thread IDs
as primary harness run IDs.

## Cursor Profile

Cursor-specific surfaces belong behind a Cursor adapter:

- Cursor SDK or CLI when real authentication is available.
- Cursor ACP for structured same-worker sessions if exposed by the runtime.
- Cursor Cloud Agents API for GitHub/PR-native async tasks when available.

Until a real Cursor account or API key authenticates the run, Cursor support
must materialize as one of these non-delivery states:

- `blocked`: required Cursor authentication is unavailable.
- `capability_probe`: generic connectivity or command discovery succeeded, but
  no Cursor execution was verified.

Do not treat Codex OpenAI-compatible configuration as Cursor execution evidence.

## ChatGPT Web Assist Profile

ChatGPT Web is not an executor profile. It is an external assist profile that
can draft:

- requirement analysis
- architecture/design suggestions
- `codex-execution-plan.json`
- candidate patches
- reports
- testing guides

Its output must be imported, validated, locally applied if appropriate, tested,
and accepted or rejected by the local supervisor receipt.

## Materialization Review

Before launching a run, the supervisor should record:

- selected executor or assist profile
- resolved model hint or human-selected model note
- materialized prompts, tools, MCP, scripts, and package boundaries
- sandbox and approval mode
- workspace/worktree policy
- credential reference or blocked credential state
- output contract version

This review record is not a replacement for `VerificationReceipt`; it proves
the run was launched with the intended runtime boundary.

## Future Packaging Rule

Materialization files must stay source-neutral and easy to install as a
project-local managed harness component. The active install boundary is a target
project's `.codex-harness/` directory plus a managed root `AGENTS.md` entry.
Do not hard-code local absolute paths, old preview branch names, product
session IDs, or one-off worker IDs in stable materialization docs. Global
installation remains outside the current boundary.
