# Task Payload Template

This template is only for the current run. Do not repeat stable harness,
Codex, ChatGPT Web, or provider-adapter rules here unless the current task is
intentionally overriding them.

## Template

```text
User request original text:

requirement_context:
- requirement_items:
- must_preserve:
- assumptions:
- open_questions:
- explicit_user_overrides:

provider_selection:
- mode: registry_default | prompt_controlled | fixed
- preferred_provider_ids:
- allowed_provider_ids:
- fallback_provider_ids:
- selection_prompt:
- resolution_policy:

delegation_policy:
- autonomy_level: plan_only | supervised_patch | supervised_act | autonomous_candidate
- context_sharing: summary_only | full_user_request_with_redactions | full_context_bundle_with_redactions
- allowed_operations:
- requires_human_confirmation:
- supervisor_gate_required: true

goal_state:
- description:
- owner: harness_supervisor | codex_thread
- sync_mode: harness_only | codex_app_server_goal_if_available
- codex_thread_id:
- source:

Current-run supervisor override:

Current-run executor override:

Current-run assist-channel override:

Required artifacts:

Verification target:

Out of scope:
```

## Fill Rules

- `User request original text` should preserve as much of the user's wording as
  practical after redacting secrets, credentials, session IDs, and unrelated
  private material. It is the primary source passed to subagents to reduce
  information loss.
- `Requirement context` decomposes the raw request into traceable requirement
  items without replacing the original text. Use stable IDs when downstream
  agents must map candidate artifacts back to user intent.
- `Provider selection` is prompt-controllable, but it resolves through the
  provider registry. A selected provider can only act at its registered
  authority level. Blocked providers produce a blocked or capability-probe
  receipt, not silent delivery.
- `Delegation policy` gives agents explicit scoped autonomy. Broader autonomy
  can permit owned-path edits, test execution, shell/browser/network use, and
  subagent spawning, but final delivery still requires the local supervisor gate.
- `Current-run supervisor override` applies only to orchestration, dispatch,
  monitoring, gates, and final acceptance for this run.
- `Current-run executor override` applies only to provider-backed execution
  units such as CodexSDK, Codex CLI, Cursor, Antigravity, Claude Code, or
  OpenCode.
- `Current-run assist-channel override` applies only to ChatGPT Web, ChatGPT
  App no-API, Antigravity manual assist, or connector-based candidate-artifact
  flows.
- If a rule repeats across many tasks, promote it into the appropriate stable
  prompt, doc, schema, validator, or tool instead of keeping it in payloads.

Provider family names such as `chatgpt`, `codex`, `cursor`, and `antigravity` are prompt intent aliases. The supervisor resolves them through registry `family_defaults`; `RunRequest.provider_selection` and execution plans should carry concrete provider IDs such as `codex_cli` or `antigravity_manual_assist`, not ambiguous family aliases.
