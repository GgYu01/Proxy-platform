# Codex Harness Prompt Group

## Purpose

This is the active prompt group for the Codex-led multi-agent coding harness.
It separates stable supervisor policy, task-local payloads, and external assist
channel instructions.

## Files

1. `codex_executor.md`
   - Stable rules for the local Codex supervisor or delegated Codex work units.
   - Covers requirement analysis, architecture/design, dispatch, execution,
     verification, receipts, and close-out governance.

2. `task_payload_template.md`
   - Current-run facts and temporary overrides only.
   - Do not repeat stable harness rules here.

3. `chatgpt_web_manual_assist.md`
   - Stable prompt for a human-operated ChatGPT Web assist channel.
   - ChatGPT Web may draft candidate plans, patches, reports, and testing
     guides, but local Codex remains the verification and delivery authority.

## Ownership

The local Codex supervisor owns intake, requirement analysis, architecture,
dispatch, integration, verification, receipts, delivery decisions, and
governance. Provider adapters own only their transport and execution details.
Assist channels own only candidate artifact drafting.


## Provider Selection And Delegation

Task payloads may include `provider_selection` so the user or supervisor can
prefer `chatgpt`, `codex`, `cursor`, or `antigravity` for a run. Selection is
prompt-controllable, but it must resolve through `configs/harness-provider-registry.json`.
A provider can only act at its registered authority level: assist channels draft
candidate artifacts, blocked future executors produce blocked or capability-probe
receipts, and local Codex remains the integration, verification, and delivery
authority.

Task payloads may include `delegation_policy` to give agents more scoped
autonomy. Broader autonomy can allow owned-path edits, shell/test/browser use,
network access, artifact packaging, and subagent spawning. It must still keep
`supervisor_gate_required: true`; no provider prompt grants final delivery
authority by itself.

Task payloads and execution plans may include `goal_state` when a long-running
supervisor objective should stay visible across executor turns. Codex SDK
adapters may mirror it through Codex app-server goal methods only after a local
probe; otherwise it remains harness-owned prompt and receipt state.

Task payloads should include `requirement_context.original_user_request` when
subagents are dispatched. Preserve as much user wording as practical after
redacting credentials and unrelated private data, then add traceable requirement
items as hints rather than replacing the original request.

Execution plans may include `workflow_context` to help downstream agents see the
original flow and prior-round summary. It is orientation context only. Unit
objective, owned paths, expected artifacts, acceptance checks, and the local
supervisor gate always override it.

## Assembly Rule

- Supervisor prompt carries orchestration and delivery policy.
- Executor prompt carries execution policy.
- Task payload carries only task-local facts and temporary overrides.
- Assist prompts carry external drafting policy only.

Do not paste stable executor rules into the task payload unless the current run
intentionally overrides them.

Provider family names such as `chatgpt`, `codex`, `cursor`, and `antigravity` are prompt intent aliases. The supervisor resolves them through registry `family_defaults`; `RunRequest.provider_selection` and execution plans should carry concrete provider IDs such as `codex_cli` or `antigravity_manual_assist`, not ambiguous family aliases.
