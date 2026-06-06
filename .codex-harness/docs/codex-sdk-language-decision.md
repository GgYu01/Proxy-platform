# Codex SDK Language Decision

Date: 2026-06-04
Status: Active adapter decision

## Local Installation Status

As of 2026-06-04, the bundled workspace Python environment has
`openai-codex@0.1.0b3` installed and importable. Its large pinned runtime
dependency `openai-codex-cli-bin` is not installed yet because PyPI and mirror
downloads were too slow in this environment. The workspace therefore uses a
local `CodexConfig.codex_bin` override for probes:
`.tmp/codex-runtime/codex.exe`, copied from the Codex Desktop WindowsApps
package. That copied binary reports `codex-cli 0.136.0-alpha.2` and can be
started by the Python SDK app-server client.

This is enough to switch local SDK development and app-server initialization to
Python. A real agent run still needs a separate authentication/thread execution
probe before the adapter may claim delivery authority.

The TypeScript SDK `@openai/codex-sdk` is not installed locally or globally in
this workspace environment.

## Decision

Keep one Codex SDK adapter direction: the official Python `openai-codex` SDK.
Do not build a TypeScript `@openai/codex-sdk` adapter for this harness unless a
future explicit reassessment shows that its public API exposes the same goal and
app-server control surface needed by the harness.

## Evidence Checked

The comparison is intentionally package-level and local-probe friendly. It does
not require a live Codex login or model run.

| Surface | TypeScript SDK | Python SDK |
|---|---|---|
| Official package inspected | `@openai/codex-sdk@0.137.0` | `openai-codex@0.1.0b3` |
| Package status | Stable-looking npm release with TypeScript types | PyPI beta release, requires `--pre` discovery |
| Runtime dependency | Depends on `@openai/codex@0.137.0` | Uses pinned `openai-codex-cli-bin` runtime dependency |
| Thread start/resume | Present | Present |
| Working directory control | `workingDirectory` in public types | `cwd` in thread APIs |
| Goal API evidence | No `goal` or `thread/goal/*` in public `index.d.ts` | Generated `ThreadGoalSet/Get/Clear` request and response models present |
| Low-level app-server RPC | Not exposed in public types inspected | `CodexClient.request(...)` sends typed JSON-RPC requests |
| Sync/async APIs | Public class surface is compact | Sync `Codex` and async `AsyncCodex` APIs present |
| Typed package marker | TypeScript declarations | `py.typed` present |
| Multi-agent related evidence | Not observed in public types inspected | `CollabAgentToolCallThreadItem` present in generated models |
| Harness fit | Good for basic thread runs, weaker for goal integration | Best fit for goal sync and Python-based harness tooling |

## Rationale

The harness is already mostly Python: validators, packager, dispatcher, probes,
and tests are Python standard-library tools. The Python Codex SDK is beta, but
it exposes the specific app-server control points the harness needs for durable
goal integration: generated goal request models plus a low-level JSON-RPC
request method. The TypeScript SDK is easier to recognize as a current npm
package, but the inspected public type surface does not expose goal operations
or a comparable app-server request escape hatch.

For this workspace, goal synchronization matters more than language popularity.
Keeping both SDK languages would create duplicate adapter semantics and twice the
verification burden. The provider registry therefore keeps a single `codex_sdk`
provider and defines it as the Python `openai-codex` adapter.

## Required Probe Before Claiming Local Support

Run:

```powershell
$python = "C:\Users\Administration\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $python tools\probe_codex_sdk_capabilities.py --output .tmp\codex-sdk-probe\receipt.json
```

The receipt must show:

- `conclusion.selected_sdk_language = "python"`
- `conclusion.adapter_policy = "keep_one_codex_sdk_adapter_python_only"`
- `python_sdk.api_surface.has_generated_goal_requests = true`
- `python_sdk.api_surface.has_low_level_json_rpc_request = true`
- `python_sdk.api_surface.has_cwd_thread_start = true`

Local execution still needs a separate authentication/runtime probe before the
adapter may claim it completed a real Codex run.
