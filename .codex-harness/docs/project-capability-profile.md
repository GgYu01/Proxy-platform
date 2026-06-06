# Project Capability Profile

Date: 2026-04-30
Updated: 2026-06-02
Status: Active Codex-led harness baseline

## Purpose

The Project Capability Profile records the reusable knowledge and tools an
executor must discover before working on a project. It prevents every run from
re-learning the same AGENTS files, skills, MCP servers, CLI tools, verification
commands, deployment paths, and governance rules.

This document defines the profile shape. Concrete projects should store the
profile next to their own source or delivery-control docs.

## Profile Shape

```yaml
project_capability_profile:
  project_id: codex_led_harness
  updated_at: "2026-06-02"

  guidance:
    agents_files:
      - AGENTS.md
    required_docs:
      - docs/codex-led-harness-architecture.md
      - docs/executor-run-contract.md
      - docs/protocol-boundaries.md
      - docs/harness-evaluation-standards-2026-06-02.md
      - docs/project-local-harness-installation.md
    prompt_groups:
      - prompt_groups/codex_harness

  skills:
    repo:
      - docs/codex-led-harness-architecture.md
    user:
      - openai-docs
      - verification-before-completion

  mcp:
    required:
      - filesystem
    optional:
      - chrome_devtools
      - context7

  cli:
    required:
      - git
      - python
    optional:
      - node
      - rg
      - jq

  executor_profiles:
    codex_multi_agent_harness:
      model_hint: gpt-5.5
      required_capabilities:
        - requirement_analysis
        - architecture_design
        - serial_parallel_dispatch
        - edit
        - shell
        - test
        - receipt
      materialization: docs/executor-materialization-profile.md
      provider_registry: configs/harness-provider-registry.json
      evaluation_registry: configs/harness-evaluation-registry.json
      project_local_installer: tools/package_harness.py
    codex_gpt55_local:
      model_hint: gpt-5.5
      status: legacy_alias
      required_capabilities:
        - edit
        - shell
        - test
      materialization: docs/executor-materialization-profile.md

  manual_assist_profiles:
    chatgpt_web_manual:
      workflow: docs/chatgpt-web-manual-assist-workflow.md
      prompt: prompt_groups/codex_harness/chatgpt_web_manual_assist.md
      validator: tools/validate_chatgpt_web_manual_assist.py
      browser_bridge: tools/chatgpt_web_simprint_bridge.py
      artifact_importer: tools/chatgpt_web_artifact_importer.py
      default_project_alias: harness-dev-test
      upload_targets:
        - conversation
        - project_sources
      storage: .tmp/chatgpt-web/
      local_supervisor_required: true
    chatgpt_app_no_api:
      workflow: docs/chatgpt-app-no-api-supervised-workflow.md
      transport: Apps SDK / MCP connector
      default_project_alias: harness-dev-test
      upload_targets:
        - conversation
        - project_sources
      storage: .tmp/chatgpt-app/
      local_supervisor_required: true
      api_model_calls_allowed: false

  verification:
    required_levels:
      - R0
      - D0
      - L0
      - L1
      - G0
    blocked_levels:
      L4: "Remote or external provider runtime unavailable unless explicitly configured for the run"
      L5: "Canary requires deployment environment"
      L6: "Production validation requires live deployment"
    commands:
      - python -m unittest tests.test_executor_contract_tools
      - python -m unittest tests.test_harness_package_tools
      - python tools/validate_harness_evaluation_registry.py configs/harness-evaluation-registry.json
      - python .codex-harness/tools/package_harness.py verify --target .

  delivery:
    artifact_requirements:
      - artifact_manifest
      - verification_receipt
      - evaluation_registry_when_benchmarks_are_used
      - project_local_install_receipt_when_installed
      - markdown_report
      - local_supervisor_receipt_when_manual_assist_is_used
    source_update_strategy:
      - keep active harness docs and validators in this workspace
      - keep removed legacy platform surfaces out of active harness entrypoints

  governance:
    inventory_doc: docs/codex_tooling_inventory.md
    closeout_required: true
```

## Review Rules

Review this profile before each substantial run:

1. Required docs still exist.
2. Required tools are available or blocked explicitly.
3. Skills are not stale or duplicated.
4. MCP servers are still appropriate for the run.
5. Verification levels are either required, skipped, or blocked with a reason.
6. Delivery artifacts are defined before executor launch.
7. Long-term asset governance is part of the done criteria.
8. Manual external assist channels are classified separately from executor
   profiles and require local supervisor receipts.
9. ChatGPT App no-API connectors are classified as external assist inboxes,
   not executor runtimes. They may submit candidate artifacts and read
   supervisor receipts, but they must not run local commands or call model APIs.
10. ChatGPT Project references must remain alias-only. The current default
    alias is `harness-dev-test`; `project_sources` uploads require manual Web UI
    confirmation and stale bundle cleanup by the user.

## Relationship To Harness Run Contract

The Project Capability Profile is stable project context.

The Harness Run Contract is per-run execution context.

Do not copy the entire profile into every user prompt. The local Codex
supervisor should resolve the profile, materialize provider-specific
configuration, and pass only the task-local facts in `RunRequest`.

## What Belongs Here

- AGENTS and local guidance files.
- Skills and MCP server names.
- CLI tools and version-sensitive commands.
- Verification commands and levels.
- Deployment or staging boundaries.
- Known environment limitations.
- Artifact and governance expectations.

## What Does Not Belong Here

- Plaintext secrets.
- One-off user instructions.
- Full vendor-specific prompt bodies.
- Temporary debugging logs.
- Executor session IDs.
- ChatGPT Web cookies, account credentials, conversation export secrets, or
  share links that grant unintended access.

## Current Task Baseline

The current Windows workspace validates the harness locally and can package it
for project-local installation under another target project's `.codex-harness/`
directory. Global installation and service management remain deferred. Cursor
execution is also deferred until real Cursor authentication is available; until
then Cursor support may only produce probes or blocked receipts.
