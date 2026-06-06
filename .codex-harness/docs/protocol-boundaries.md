# Protocol Boundaries

Date: 2026-04-30
Updated: 2026-06-02
Status: Active Codex-led harness baseline

## Decision

The local Codex supervisor must call executors or assist channels through the
provider-neutral Harness Run Contract. Provider-specific protocols stay behind
adapter boundaries or candidate-artifact inboxes.

## Boundary Table

| Boundary | Protocol / Shape | Owner | Notes |
|---|---|---|---|
| User -> local Codex supervisor | Codex thread / task prompt | Local Codex supervisor | User describes the goal; supervisor derives scope, design, dispatch, and verification. |
| Supervisor -> Python Codex SDK / Codex CLI | Harness Run Contract + provider adapter | Local Codex supervisor | Python `openai-codex` SDK is the selected SDK adapter; Codex CLI is the fallback local execution path. |
| Supervisor -> Cursor | Harness Run Contract + Cursor adapter | Local Codex supervisor | Future path. Requires real Cursor authentication; otherwise blocked receipt only. |
| Supervisor -> Antigravity manual assist | Prompt-selected candidate-artifact assist | Human operator + local Codex supervisor | External assist only. Not delivery evidence until locally verified. |
| Supervisor -> Antigravity agent | Harness Run Contract + provider adapter | Local Codex supervisor | Future path. Requires real Antigravity authentication and execution receipts; otherwise blocked receipt only. |
| Supervisor -> Claude Code / OpenCode | Harness Run Contract + provider adapter | Local Codex supervisor | Future executors; must emit the same contract semantics. |
| Supervisor -> reviewer agents | ReviewVerdict | Local Codex supervisor | Reviewers challenge results but cannot bypass the supervisor gate. |
| Executor -> tools/context | MCP / local tools / scripts | Executor runtime | MCP is for tools and context, not run lifecycle. |
| Executor -> editor agent | ACP | Executor adapter | ACP is a client-agent session protocol, not the harness state machine. |
| Local supervisor -> ChatGPT Web | Manual browser upload/download packet | Human operator + local Codex supervisor | External assist only. Not a Harness Run Contract executor adapter and not delivery evidence until locally verified. |
| ChatGPT Web -> project assist inbox | ChatGPT App connector over Apps SDK / MCP | Human operator + connector backend | No API model calls in no-API mode. Connector stores candidate artifacts and exposes supervisor receipts; it must not run Codex, shell, git, or deploy. |

## Rules

1. Do not put Cursor ACP, Cursor CLI, Cursor Cloud API, Codex CLI, Claude Code,
   OpenCode, or provider-specific Cloud API fields in harness task payloads.
2. Do not treat MCP as the executor lifecycle protocol.
3. Do not treat executor natural-language completion as delivery.
4. Do not allow reviewers to bypass the supervisor and call provider surfaces
   directly.
5. Do not expose OpenAI response IDs, Codex thread IDs, Claude session IDs, or
   Cursor ACP IDs as primary harness run IDs.
6. Treat unknown fields in `RunRequest` as contract violations. Use explicit
   provider-neutral containers such as `requirement_context`, `provider_selection`,
   and `delegation_policy` instead of ad hoc fields. Vendor-specific IDs,
   commands, sessions, and protocol handles must be stored inside adapter state
   or artifacts, not inside the harness task payload.
7. Treat ChatGPT Web manual assistance as an external drafting channel. Do not
   save ChatGPT account credentials, cookies, browser sessions, or share links
   as project assets. A real ChatGPT conversation URL or id may be stored only
   as explicit opt-in local private adapter state for operator navigation; it
   must not enter run contracts, upload packets, receipts, tracked docs, or
   model-visible prompts. Do not mark ChatGPT Web output delivered until local
   Codex supervisor verification passes.
8. Treat ChatGPT App no-API connectors as controlled inboxes, not executor
   runtimes. They may accept candidate artifacts from ChatGPT Web and expose
   local supervisor receipts, but they must not call OpenAI model APIs, start
   Codex, run shell commands, apply patches to the real repository, commit,
   merge, or deploy.
9. Treat Antigravity manual assist like other assist channels: it may draft
   candidate artifacts from sanitized context, but it must not receive delivery
   authority, tracked credentials, session handles, or unverified execution
   claims.

## Why This Matters

The root cause of prior confusion is boundary collapse. Once provider session
details leak into task payloads, every executor adds a new branch to the
harness state machine. That makes review, artifact relay, cancellation, retry,
verification, and delivery inconsistent.

The harness needs stable semantics:

- `run_id`
- idempotency
- lease
- progress events
- artifacts
- verification receipt
- reviewer verdict
- delivery gate
- cancel/resume/retry

Vendor protocols can still be used aggressively inside adapters. They just
cannot define the harness state model.


Provider choice can be controlled by prompt intent through `provider_selection`.
The supervisor resolves aliases such as `chatgpt`, `codex`, `cursor`, and
`antigravity` against the provider registry. A blocked or assist-only provider
selection is preserved as evidence and downgrade state; it is not silently
converted into verified execution.

## Allowed Adapter Internals

Codex adapter may use:

- CodexSDK, defined only as the official Python `openai-codex` SDK adapter
- Codex CLI
- Codex app/IDE configuration
- Codex skills
- Codex MCP server
- OpenAI Agents SDK
- OpenAI Responses API

Cursor adapter may use:

- Cursor ACP
- Cursor CLI headless
- Cursor Cloud Agents API

Cursor adapter must not be marked verified unless a real Cursor account or
Cursor API key authenticated the run. Codex OpenAI-compatible configuration can
help probe generic model connectivity, but it is not evidence of Cursor agent
execution.

Claude Code adapter may use:

- Claude Code subagents
- Claude Code hooks
- Claude Code skills
- Claude Code plugins

OpenCode adapter may use:

- OpenCode CLI
- OpenCode plugin/runtime features

Manual ChatGPT Web assist may use:

- private ChatGPT project or private chat
- manually uploaded sanitized packets from `.tmp/`
- downloaded or copied patch/report artifacts
- local supervisor receipts produced after independent verification

ChatGPT App no-API assist may use:

- Apps SDK / MCP tool calls from a user-operated ChatGPT Web conversation
- a restricted HTTPS `/mcp` connector backend
- `.tmp/chatgpt-app/<run_id>/` as a candidate artifact inbox
- local supervisor receipts written by Codex after independent verification

Every executor adapter must normalize output into:

- `RunEvent`
- `ArtifactManifest`
- `VerificationReceipt`
- `RunResult`

Manual ChatGPT Web assist is different: it must produce a manual-assist
response packet and then a local supervisor receipt. It must not produce
`RunResult` directly.

ChatGPT App no-API assist is also different from an executor adapter. It may
replace manual upload/download with structured tool calls, but it still must
not produce `RunResult` directly.

## ChatGPT Project And Conversation Aliases

For ChatGPT Web assisted runs, a local `relationship-map.json` may bind a Codex
supervisor run to a user-visible ChatGPT Project alias and a user-visible
conversation alias. These aliases are for human coordination only.

Allowed local fields in tracked or uploaded artifacts:

- `run_id`, `attempt_id`, and registered `workspace_id`.
- `codex_thread_ref`, `chatgpt_project_alias`, and `chatgpt_conversation_alias`
  when they are plain user-visible labels.
- `upload_target` when it is either `conversation` or `project_sources`.
- Source bundle hash, file count, total byte count, and retention notes for
  manually uploaded Project-source bundles.
- ChatGPT Web manual-assist `chatgpt_model_policy` when it records only
  user-visible model labels, the current UI thinking-effort rank
  `快速 < 标准 < 进阶 < 深入 < Extended`, model-specific visible options,
  and a UI availability probe policy. Critical GPT-5.5 Pro stages require
  `Extended` evidence and must block instead of downgrading when it is absent.
  This is operator guidance, not an API model selector.
- Local paths to sanitized upload bundles, manifests, prompts, imported
  responses, and supervisor receipts.
- Local supervisor status derived from independent verification.

`project_sources` means the user manually uploads the sanitized source bundle
into the ChatGPT Project's persistent product-side file/source context.
`conversation` means the files are only current-conversation attachments. Local
CDP or Simprint automation may help fill a page, but it must not be treated as
proof that Project sources were updated. The user must confirm Project-source
uploads in the ChatGPT Web UI.

Forbidden fields in tracked or uploaded artifacts:

- ChatGPT account credentials, cookies, browser sessions, localStorage,
  OAuth tokens, or share links.
- Real ChatGPT Project IDs, conversation IDs, session IDs, or any product-side
  handle that could be treated as a reusable control token.
- API keys, SSH private keys, database passwords, or deployment credentials.
- `model`, `reasoning_effort`, `api_key`, or similar fields in no-API connector
  packets, because model selection belongs to the user-operated ChatGPT Web
  conversation, not the local connector backend.

Optional private adapter state may store a real ChatGPT conversation URL or
opaque conversation id only when the user explicitly opts in. That state must
stay under an ignored local path such as `.tmp/chatgpt-app/private/`, include a
TTL or expiry, and be used only to help the human/local operator reopen or
continue the Web conversation. It must not be copied into upload manifests,
request packets, response artifacts, supervisor receipts, reports, package
exports, or Git commits.

## Partial Test Exception

When a provider account, SDK, remote API, or deployment environment is missing,
that only relaxes the unavailable end-to-end check. It does not relax contract
validation, schema checks, local unit tests, or documentation governance. The
receipt must mark the unavailable path as `blocked` instead of pretending it
passed.

Provider family names such as `chatgpt`, `codex`, `cursor`, and `antigravity` are prompt intent aliases. The supervisor resolves them through registry `family_defaults`; `RunRequest.provider_selection` and execution plans should carry concrete provider IDs such as `codex_cli` or `antigravity_manual_assist`, not ambiguous family aliases.
