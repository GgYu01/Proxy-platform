# Platform State And Projections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first platform-state layer to `proxy-platform`, including host registry ingestion, observed-state merge, subscription projections, local provider policies, CLI read models, and a minimal web console.

**Architecture:** Keep `proxy-platform` as a thin orchestration shell. Read real host inventory from the operator/private side, merge it with optional observed-state inputs, derive subscription links and host views inside this repo, and expose the result through CLI and a minimal web adapter. Do not add remote apply logic in this phase.

**Tech Stack:** Python 3.9+, PyYAML, FastAPI, Uvicorn, pytest

---

### Task 1: Add formal design and boundary docs

**Files:**
- Create: `docs/plans/2026-04-14-platform-state-and-projections-design.md`
- Create: `docs/adr/ADR-0008-hybrid-host-registry-and-derived-platform-views.md`
- Modify: `docs/agent-governance/project/README.md`
- Modify: `docs/review-checklists/platform-shell.md`

- [ ] **Step 1: Write the docs**

Describe:
- expected vs observed state
- repository ownership boundaries
- why subscriptions are projections
- why remote apply stays out of phase 1

- [ ] **Step 2: Review for consistency**

Check that the docs align with existing ADR-0001/0002 and do not redefine `proxy-platform` as a new control-plane kernel.

### Task 2: Extend manifest for state sources and local provider budgets

**Files:**
- Modify: `platform.manifest.yaml`
- Modify: `src/proxy_platform/manifest.py`
- Modify: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert:
- manifest can parse a host registry source
- manifest can parse an observation source
- manifest can parse local provider policies with startup timeout set to 15 seconds

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_manifest.py -q`
Expected: FAIL because the new manifest sections are not implemented.

- [ ] **Step 3: Implement minimal parsing and validation**

Add manifest support for:
- host registry file paths
- subscription config file paths
- observed-state file paths
- local provider lifecycle policies

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_manifest.py -q`
Expected: PASS

### Task 3: Add host registry and subscription projection modules

**Files:**
- Create: `src/proxy_platform/inventory.py`
- Create: `src/proxy_platform/projections.py`
- Create: `tests/test_inventory.py`
- Create: `tests/test_projections.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- reading real-style node inventory
- merging optional observed-state records
- deriving multi-node and per-node subscription URLs
- keeping disabled hosts out of publishable projections while still allowing them to appear in registry output

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_inventory.py tests/test_projections.py -q`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement minimal code**

Implement:
- host record loading
- observation merge
- host view derivation
- subscription projection derivation

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_inventory.py tests/test_projections.py -q`
Expected: PASS

### Task 4: Add CLI commands for hosts, subscriptions, and providers

**Files:**
- Modify: `src/proxy_platform/cli.py`
- Create: `src/proxy_platform/providers.py`
- Modify: `tests/test_cli.py`
- Create: `tests/test_providers.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:
- `hosts list`
- `subscriptions list`
- `providers list`

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_cli.py tests/test_providers.py -q`
Expected: FAIL because the commands do not exist.

- [ ] **Step 3: Implement minimal command behavior**

Expose:
- host table output with expected/observed fields
- subscription URL output with copy-friendly lines
- local provider policy output with retry/timeout budgets

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_cli.py tests/test_providers.py -q`
Expected: PASS

### Task 5: Add minimal web console

**Files:**
- Add: `src/proxy_platform/web_app.py`
- Modify: `src/proxy_platform/__main__.py`
- Modify: `apps/web-console/README.md`
- Add: `tests/test_web_app.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert:
- `/api/hosts` returns merged host view JSON
- `/api/subscriptions` returns derived subscription links
- `/` returns HTML containing host names and subscription URLs

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_web_app.py -q`
Expected: FAIL because the web app does not exist.

- [ ] **Step 3: Implement minimal web adapter**

Provide:
- JSON endpoints for hosts, subscriptions, and providers
- simple HTML page with copy buttons
- local inventory add/remove endpoints only

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_web_app.py -q`
Expected: PASS

### Task 6: Update user entry docs and governance docs

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `progress.md`

- [ ] **Step 1: Update docs**

Document:
- platform-state role
- new commands
- local provider timeout/retry budgets
- web console scope and current mutation boundary

- [ ] **Step 2: Add governance guidance**

Add explicit rules for:
- when logic belongs in `proxy-platform`
- when it stays in `remote_proxy`
- when it stays in `Proxy_ops_private`
- why generated subscriptions are not source-of-truth

### Task 7: Verify end-to-end

**Files:**
- Modify: `progress.md`

- [ ] **Step 1: Run full test suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 2: Run CLI smoke checks**

Run: `python -m proxy_platform hosts list`
Expected: prints merged host registry view

Run: `python -m proxy_platform subscriptions list`
Expected: prints multi-node and per-node subscription URLs

Run: `python -m proxy_platform providers list`
Expected: prints local provider retry/timeout policies

- [ ] **Step 3: Run web smoke check**

Run: `python -m proxy_platform web --host 127.0.0.1 --port 8765`
Expected: local web console starts successfully

- [ ] **Step 4: Record verification evidence**

Update `progress.md` with commands, exit codes, and what was proven.
