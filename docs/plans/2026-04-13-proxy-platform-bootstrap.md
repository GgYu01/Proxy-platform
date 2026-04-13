# Proxy Platform Bootstrap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first shippable thin-shell `proxy-platform` repository with platform governance docs, manifest, and a testable CLI surface, including safe local workspace materialization from local overrides.

**Architecture:** Keep the repository as a thin orchestration shell. The runtime logic lives in existing repos; this repo only models repo topology, validates workspace state, and exposes user-facing commands. The first implementation is CLI-first, with Web reserved as a future adapter layer.

**Tech Stack:** Python 3.9+, stdlib argparse, PyYAML, pytest

---

### Task 1: Establish repository metadata and governance files

**Files:**
- Create: `AGENTS.md`
- Create: `README.md`
- Create: `.gitignore`
- Create: `platform.manifest.yaml`
- Create: `docs/adr/ADR-0001-thin-shell-platform.md`
- Create: `docs/adr/ADR-0002-private-ops-boundary.md`
- Create: `docs/adr/ADR-0003-control-plane-remains-northbound-kernel.md`
- Create: `docs/adr/ADR-0004-remote-browser-provider-slot.md`
- Create: `docs/adr/ADR-0005-submodule-plus-manifest.md`

**Step 1: Write failing tests**

- Add tests that validate manifest parsing and required repo entries.

**Step 2: Run tests to verify failure**

Run: `pytest -q`
Expected: fail because manifest loader and CLI do not exist yet.

**Step 3: Create governance and architecture docs**

- Write the platform-level AGENTS rules and ADR set matching the approved design.

**Step 4: Re-run tests**

Run: `pytest -q`
Expected: still fail only on missing runtime implementation.

### Task 2: Implement manifest model and repo status detection

**Files:**
- Create: `src/proxy_platform/manifest.py`
- Create: `src/proxy_platform/workspace.py`
- Create: `tests/test_manifest.py`
- Create: `tests/test_workspace.py`

**Step 1: Write the failing test**

- Test required repo entries, public/private flags, optional repos, and local path status detection.

**Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_manifest.py tests/test_workspace.py -q`
Expected: fail because implementation modules do not exist.

**Step 3: Write minimal implementation**

- Parse `platform.manifest.yaml`
- Detect repo presence/status in workspace
- Support `public` and `operator` modes

**Step 4: Run targeted tests**

Run: `pytest tests/test_manifest.py tests/test_workspace.py -q`
Expected: PASS

### Task 3: Implement CLI thin shell

**Files:**
- Create: `src/proxy_platform/cli.py`
- Create: `src/proxy_platform/__init__.py`
- Create: `src/proxy_platform/__main__.py`
- Create: `tests/test_cli.py`
- Create: `pyproject.toml`

**Step 1: Write the failing test**

- Cover `repos list`, `manifest validate`, `doctor`, `init --dry-run`, `sync --dry-run`.

**Step 2: Run targeted tests to verify failure**

Run: `pytest tests/test_cli.py -q`
Expected: fail because CLI entrypoints do not exist.

**Step 3: Write minimal implementation**

- Provide deterministic stdout for the command set
- Keep destructive behavior disabled; only local workspace linking/status/report in first wave

**Step 4: Run targeted tests**

Run: `pytest tests/test_cli.py -q`
Expected: PASS

### Task 4: Verify full repository health

**Files:**
- Modify: `README.md`
- Modify: `progress.md`

**Step 1: Run the full test suite**

Run: `pytest -q`
Expected: PASS

**Step 2: Run CLI smoke checks**

Run: `python -m proxy_platform manifest validate`
Expected: manifest validates successfully

Run: `python -m proxy_platform repos list`
Expected: repo list prints current workspace topology

Run: `python -m proxy_platform doctor`
Expected: diagnostic summary without destructive actions

**Step 3: Update progress log**

- Record verification commands and outcomes.
