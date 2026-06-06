# Codex-Led Multi-Agent Harness Architecture

Date: 2026-06-02
Status: Active baseline

## Decision

This workspace now uses a local Codex-led coding harness as the active system.
It prepares work, coordinates implementation agents, verifies results, records
receipts, and preserves reusable lessons.

The previous platform-specific architecture is removed from active prompts,
tools, contracts, and default documentation entrypoints. Reintroducing it would
be a new explicit task, not an implicit fallback.

## Primary Goal

Build a supervised coding automation flow that can:

1. Prepare code context, create the run contract, orchestrate the main control
   flow, and monitor the full run over time.
2. Analyze user requirements and convert them into concrete scope, acceptance
   criteria, risks, and verification obligations.
3. Produce architecture and design, including serial or parallel work
   orchestration and the prompts needed for each work unit.
4. Execute tests, compare failures with the design, request or perform repairs,
   package code and debug bundles, and exchange logs or diagnostics with assist
   channels.
5. Summarize run execution, write durable receipts and traces, and introduce
   public benchmark or harness evaluation mechanisms where useful. Automatic
   repair loops are deferred until the evidence and gate model are stable.

## Required Cross-Cutting Modules

### Run Contract And State Machine

Every run needs a structured contract with `run_id`, raw requirement context,
task objective, scope hints, allowed paths, worktree policy, delegation policy,
provider selection, dispatch graph, required artifacts, verification commands,
and acceptance criteria. The event stream must separate executor progress from
supervisor delivery decisions.

### Provider Adapter Registry

Adapters describe capability, not authority. A provider profile must state
whether it can read files, write files, run commands, produce patches, dispatch
parallel units, stream logs, or require a human operator.

Initial adapter policy:

- `codex_sdk`: preferred real execution path for local supervised runs when the
  official Python `openai-codex` SDK is available. The harness keeps one Codex
  SDK adapter direction only: Python. The inspected Python package
  `openai-codex@0.1.0b3` is beta but exposes typed generated
  `thread/goal/set`, `thread/goal/get`, and `thread/goal/clear` request models,
  a low-level JSON-RPC `request(...)` client, sync and async API classes,
  `cwd` thread options, a typed package marker, collab-agent thread items, and a
  pinned `openai-codex-cli-bin` runtime dependency. The inspected TypeScript
  package `@openai/codex-sdk@0.137.0` exposes thread start/resume and
  `workingDirectory`, but its public types do not expose goal requests or a
  comparable low-level app-server RPC surface, so it is not selected for the
  harness adapter.
- `codex_cli`: fallback local execution path and current dispatcher backend.
- `chatgpt_web_manual`: candidate-artifact assist only; it cannot claim local
  verification or delivery.
- `chatgpt_app_no_api`: structured candidate-artifact inbox and receipt reader;
  it cannot run shell, Codex, git, deploy, or model API calls.
- `cursor_sdk` / `cursor_cli`: future adapter. Without real Cursor account
  authentication, it may only emit capability probes or blocked receipts.
  Reusing Codex OpenAI-compatible configuration is not a valid Cursor execution
  proof.
- `antigravity_manual_assist`: candidate-artifact assist only. It may be
  prompt-selected for critique, plans, patches, or reports, but cannot claim
  local verification or delivery.
- `antigravity_agent`: future adapter. It remains blocked until real
  Antigravity authentication and execution receipts exist.

The machine-readable provider source is
`configs/harness-provider-registry.json`; validate it with
`tools/validate_harness_provider_registry.py`.


### Requirement Context And Delegation

The supervisor should pass most of the original user request to subagents through
`requirement_context.original_user_request`, after redacting secrets and
unrelated private material. Structured requirement items, assumptions, open
questions, and acceptance criteria are hints and traceability aids; they should
not erase the original wording.

Execution plans may also include `workflow_context` for downstream agents. It
summarizes the original end-to-end flow, prior rounds, the current round, and
drift guards so agents can use broader model reasoning without losing the local
unit boundary. `workflow_context` is background only: unit objective, owned
paths, expected artifacts, acceptance checks, and the supervisor gate always
override it.

`provider_selection` lets prompts prefer ChatGPT, Codex, Cursor, or Antigravity.
The registry still decides whether that preference is available, blocked,
future-only, or assist-only. Prompt selection never upgrades provider authority.

`delegation_policy` is the autonomy envelope. It can grant agents explicit
operations such as owned-path edits, tests, shell, browser, network, artifact
packaging, and subagent spawning. It cannot remove the local supervisor gate.

`goal_state` is supervisor-owned long-running objective state. Executors may use
it to keep a Codex thread aligned across turns, but it does not replace
`objective` for a specific run. The default sync mode for Codex SDK is
`codex_app_server_goal_if_available`; the Python SDK adapter should implement it
through generated `ThreadGoal*` request models or low-level JSON-RPC after a
local capability probe. If the probe fails, the harness keeps the goal as
`harness_only` state and continues to inject it in run prompts and receipts.

### Workspace Packaging And Isolation

The harness owns workspace selection, dirty-state capture, context cropping,
source bundles, redaction, debug bundles, isolated worktrees, rollback, and
artifact hashes. External assist channels receive only scoped packages and never
become the source of truth for local repository state.

The harness can also be packaged and installed into another Codex-opened
project as a project-local component under `.codex-harness/`. The target
project receives a managed `AGENTS.md` entry that points Codex at the installed
harness docs, configs, prompts, schemas, tools, and receipts. This installation
path is intentionally not global: it does not write `$CODEX_HOME`, global
skills, global MCP configuration, or system services.

### Scheduler, Merge, And Conflict Control

The design phase must produce a serial/parallel dispatch graph. Each unit needs
owned paths, dependencies, expected artifacts, and merge strategy. The
supervisor detects conflicts, orders integration, runs checks after merge, and
records rollback or rework decisions.

### Verification And Evaluation

Verification covers schema checks, static checks, tests, integration checks,
scenario checks, and governance review. Evaluation is a separate long-term
asset: golden tasks, public benchmark mappings, failure samples, scoring rules,
and comparison reports. The first stable version records failures and repair
requests; automatic repair is a later capability.

### Observability And Receipts

The harness records prompts, provider choice, token/cost estimates when
available, elapsed time, command output, stdout/stderr tails, artifact hashes,
verification results, user corrections, skipped checks, blocked checks, and
final decisions. Natural-language summaries are secondary to receipts and
traceable evidence.

### Human Gates

Human confirmation remains required for sensitive external upload, applying
untrusted patches, dangerous local commands, commit/push, deployment, and final
delivery when verification is incomplete or blocked.

## Active Delivery Principle

The local Codex supervisor is the delivery authority. External agents and Web
channels can draft designs, patches, reports, or work-unit plans, but the
supervisor must validate, integrate, test, and write the final receipt before
any work is represented as accepted.

## Packaging Status

Project-local packaging is active. Use `tools/package_harness.py pack` to
create `codex-project-harness.zip`, `tools/package_harness.py install` to place
it under a target project's `.codex-harness/`, and
`tools/package_harness.py verify` to check asset hashes, managed `AGENTS.md`,
provider registry, evaluation registry, and active alignment.

Global installation, service management, and automatic benchmark-runner
deployment remain deferred.

Provider family names such as `chatgpt`, `codex`, `cursor`, and `antigravity` are prompt intent aliases. The supervisor resolves them through registry `family_defaults`; `RunRequest.provider_selection` and execution plans should carry concrete provider IDs such as `codex_cli` or `antigravity_manual_assist`, not ambiguous family aliases.
