#!/usr/bin/env python3
"""Runnable demo for Codex thread, ChatGPT Project, and Web conversation mapping.

This demo intentionally uses only user-visible aliases for ChatGPT-side
entities. It never reads or stores ChatGPT cookies, browser storage, share URLs,
or private product IDs. ChatGPT Web can analyze the generated upload bundle and
draft artifacts; local Codex remains the only component that applies patches and
writes the supervisor receipt.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chatgpt_app_no_api_common import AssistError, reject_secret_text, safe_chatgpt_alias, safe_id, write_json_file
from chatgpt_web_harness import (
    DEFAULT_CHATGPT_PROJECT_ALIAS,
    DEFAULT_UPLOAD_TARGET,
    UPLOAD_TARGETS,
    apply_web_run,
    import_web_run,
    prepare_web_run,
)
from chatgpt_web_execution_dispatcher import dispatch_execution_plan, load_execution_plan_from_response


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_ROOT = ROOT / ".tmp" / "chatgpt-web-project-conversation-demo"
WORKSPACE_ID = "demo_workspace"
TASK_ID = "project_conversation_demo"

INITIAL_MODULE = """def greeting() -> str:
    return "old"
"""

UPDATED_MODULE = """def greeting() -> str:
    return "new"
"""

TEST_MODULE = """import unittest

import demo_module


class DemoModuleTests(unittest.TestCase):
    def test_greeting(self) -> None:
        self.assertEqual(demo_module.greeting(), "new")
"""

JSON = dict[str, Any]
def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("project-demo-%Y%m%dT%H%M%SZ")


def walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(walk_keys(child))
    return keys


def _safe_alias(value: str, label: str) -> str:
    return safe_chatgpt_alias(value, label)


def _require_under(path: Path, parent: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as exc:
        raise AssistError(f"{label} must stay under {parent}") from exc
    return resolved


def _run_id(run_id: str | None) -> str:
    return safe_id(run_id or default_run_id(), "run_id")


def _run_dir(demo_root: str | Path | None, run_id: str) -> Path:
    base = Path(demo_root).resolve() if demo_root else DEFAULT_DEMO_ROOT.resolve()
    return _require_under(base / run_id, base, "demo run directory")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _remove_tree(path: Path) -> None:
    def onerror(function, item, exc_info):
        try:
            os.chmod(item, stat.S_IWRITE)
            function(item)
        except OSError as exc:
            raise AssistError(f"failed to remove demo path: {item}") from exc

    shutil.rmtree(path, onerror=onerror)


def _run_git(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr).strip()
        raise AssistError(f"git command failed: {' '.join(command)}\n{output}")


def _init_demo_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    _write_text(workspace / "demo_module.py", INITIAL_MODULE)
    _write_text(workspace / "test_demo_module.py", TEST_MODULE)
    _run_git(["git", "init"], workspace)
    _run_git(["git", "add", "demo_module.py", "test_demo_module.py"], workspace)
    _run_git(
        [
            "git",
            "-c",
            "user.name=Codex Demo",
            "-c",
            "user.email=codex-demo@example.invalid",
            "commit",
            "-m",
            "init demo workspace",
        ],
        workspace,
    )


def _write_registry(storage: Path, workspace: Path) -> None:
    write_json_file(
        storage / "workspace-registry.json",
        {
            "workspaces": [
                {
                    "workspace_id": WORKSPACE_ID,
                    "display_name": "ChatGPT Web project conversation demo workspace",
                    "description": "A minimal local repo for demonstrating Web-drafted artifacts and Codex verification.",
                    "root": str(workspace),
                    "include_paths": ["demo_module.py", "test_demo_module.py"],
                    "exclude_patterns": [".git/**", ".tmp/**", "tmp/**", ".env*", "secrets/**"],
                    "max_files": 20,
                    "max_file_bytes": 200000,
                    "max_total_bytes": 500000,
                }
            ]
        },
    )


def _project_instructions(project_alias: str, upload_target: str) -> str:
    return f"""# ChatGPT Project Instructions

Project alias: `{project_alias}`
Default source mode: `{upload_target}`

You only handle task analysis, source reading, work decomposition, and candidate artifact drafting in this Project. Treat the Project as ChatGPT product-side context: it can hold uploaded reference files, project instructions, and conversations, but it is not local execution authority and it is not the real Git repository.

Hard boundaries:
- Do not claim that you accessed the user's local filesystem, ran local tests, applied patches locally, committed Git changes, or deployed anything.
- Do not ask for cookies, browser sessions, OAuth tokens, share links, API keys, SSH private keys, or account passwords.
- Work only from the uploaded `source-files.zip`, manifest, request, and the current conversation content.
- If files are uploaded to Project sources, treat them as read-only reference context. Each local run still needs a dedicated Web conversation.
- Return all outputs as `ARTIFACT: <filename>` blocks for local Codex supervisor import.
- Always include `codex-execution-plan.json`, `report.md`, `changes.patch`, and `testing-guide.md`.
"""


def _conversation_start(project_alias: str, conversation_alias: str, run_id: str) -> str:
    return f"""# ChatGPT Web Conversation Kickoff

Project alias: `{project_alias}`
Conversation alias: `{conversation_alias}`
Run id: `{run_id}`

Treat this conversation as the only working surface for this local run. You may use ChatGPT Web file analysis and container capabilities to inspect the uploaded bundle and draft candidate artifacts. Do not store or request any ChatGPT internal conversation ID, share URL, cookie, token, or browser storage content.

Task: change `demo_module.greeting()` from returning `old` to returning `new`.

Return exactly these artifacts:

```text
ARTIFACT: codex-execution-plan.json
<complete JSON plan with packet_type codex_execution_plan, language en, English runtime text, serial/parallel dispatch hints, and acceptance_checks>

ARTIFACT: report.md
<brief candidate report; do not claim local tests were run>

ARTIFACT: changes.patch
<complete unified diff>

ARTIFACT: testing-guide.md
<local test plan for Codex supervisor>

LIMITATIONS:
- No local tests were run inside ChatGPT Web.
```

Local Codex supervisor will import your artifacts, validate the execution plan, record a dispatch receipt, apply the patch, run `test_demo_module.py`, and write `local-supervisor-receipt.json`.
"""


def _relationship_map(
    *,
    run_id: str,
    codex_thread_ref: str,
    project_alias: str,
    conversation_alias: str,
    upload_target: str,
    run_path: Path,
    workspace: Path,
    storage: Path,
    prepared: JSON,
) -> JSON:
    return {
        "packet_type": "chatgpt_web_project_conversation_map",
        "created_at": now_iso(),
        "run_id": run_id,
        "attempt_id": "attempt-001",
        "refs_are_user_visible_aliases": True,
        "relationships": {
            "codex_thread_ref": codex_thread_ref,
            "chatgpt_project_alias": project_alias,
            "chatgpt_conversation_alias": conversation_alias,
            "local_workspace_id": WORKSPACE_ID,
        },
        "session_mapping_policy": {
            "one_local_run_to_one_chatgpt_conversation": True,
            "conversation_alias_is_not_a_chatgpt_id": True,
            "project_alias_is_not_a_chatgpt_id": True,
        },
        "chatgpt_upload": {
            "target": upload_target,
            "project_sources_are_persistent_product_context": upload_target == "project_sources",
            "manual_upload_confirmation_required": True,
            "source_bundle_review_required": True,
            "run_identity": prepared["run_identity"],
            "upload_files": json.loads(Path(prepared["upload_manifest"]).read_text(encoding="utf-8"))["upload_files"],
            "source_bundle_sha256": prepared["bundle"]["bundle_sha256"],
            "source_file_count": prepared["bundle"]["file_count"],
            "source_total_bytes": prepared["bundle"]["total_bytes"],
            "retention_note": "If uploaded to Project sources, the user must manually remove stale bundles from ChatGPT when they should no longer be project context.",
        },
        "local_authority": {
            "supervisor": "Codex local supervisor",
            "workspace_root": str(workspace),
            "storage_root": str(storage),
            "receipt_is_delivery_gate": True,
        },
        "chatgpt_product_roles": {
            "project": "Persistent ChatGPT product workspace for files, instructions, and related conversations.",
            "conversation": "Per-run working chat inside the Project; the user manually selects the model and confirms uploads/sends.",
        },
        "safe_artifacts": {
            "project_instructions_file": str(run_path / "chatgpt-project-instructions.md"),
            "conversation_start_file": str(run_path / "chatgpt-conversation-start.md"),
            "upload_manifest_file": str(Path(prepared["upload_manifest"]).resolve()),
            "prompt_file": str(Path(prepared["prompt_file"]).resolve()),
            "source_bundle_file": str(Path(prepared["bundle"]["bundle_path"]).resolve()),
            "source_manifest_file": str(storage / run_id / "source-files-manifest.json"),
            "request_file": str(Path(prepared["request_file"]).resolve()),
        },
        "privacy_boundary": {
            "stores_only_aliases": True,
            "manual_user_confirmation_required": True,
            "chatgpt_web_is_not_local_executor": True,
            "connector_or_browser_bridge_must_not_apply_patch": True,
        },
        "status": "prepared",
    }


def _load_mapping(run_path: Path) -> JSON:
    mapping_path = run_path / "relationship-map.json"
    try:
        payload = json.loads(mapping_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise AssistError(f"missing relationship map: {mapping_path}") from exc
    if not isinstance(payload, dict):
        raise AssistError("relationship map must be a JSON object")
    return payload


def _write_mapping(run_path: Path, payload: JSON) -> None:
    write_json_file(run_path / "relationship-map.json", payload)


def prepare_demo(
    *,
    demo_root: str | Path | None = None,
    run_id: str | None = None,
    codex_thread_ref: str = "codex-thread-local-demo",
    chatgpt_project_alias: str = DEFAULT_CHATGPT_PROJECT_ALIAS,
    chatgpt_conversation_alias: str = "demo-conversation-001",
    upload_target: str = DEFAULT_UPLOAD_TARGET,
    force: bool = False,
) -> JSON:
    run_id = _run_id(run_id)
    codex_thread_ref = _safe_alias(codex_thread_ref, "codex_thread_ref")
    project_alias = _safe_alias(chatgpt_project_alias, "chatgpt_project_alias")
    conversation_alias = _safe_alias(chatgpt_conversation_alias, "chatgpt_conversation_alias")
    if upload_target not in UPLOAD_TARGETS:
        raise AssistError(f"upload_target must be one of: {', '.join(sorted(UPLOAD_TARGETS))}")
    run_path = _run_dir(demo_root, run_id)
    base = run_path.parent
    if run_path.exists():
        if not force:
            raise AssistError(f"demo run already exists: {run_path}")
        _require_under(run_path, base, "demo run directory")
        _remove_tree(run_path)

    workspace = run_path / "workspace"
    storage = run_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    _init_demo_workspace(workspace)
    _write_registry(storage, workspace)

    prepared = prepare_web_run(
        objective="Use ChatGPT Web to draft a patch changing demo_module.greeting() from old to new.",
        workspace_id=WORKSPACE_ID,
        run_id=run_id,
        task_id=TASK_ID,
        paths=["demo_module.py", "test_demo_module.py"],
        storage=storage,
        chatgpt_project_alias=project_alias,
        chatgpt_conversation_alias=conversation_alias,
        upload_target=upload_target,
    )
    project_instructions = run_path / "chatgpt-project-instructions.md"
    conversation_start = run_path / "chatgpt-conversation-start.md"
    _write_text(project_instructions, _project_instructions(project_alias, upload_target))
    _write_text(conversation_start, _conversation_start(project_alias, conversation_alias, run_id))

    mapping = _relationship_map(
        run_id=run_id,
        codex_thread_ref=codex_thread_ref,
        project_alias=project_alias,
        conversation_alias=conversation_alias,
        upload_target=upload_target,
        run_path=run_path,
        workspace=workspace,
        storage=storage,
        prepared=prepared,
    )
    _write_mapping(run_path, mapping)
    return {
        "ok": True,
        "run_id": run_id,
        "demo_run_dir": str(run_path),
        "workspace_root": str(workspace),
        "storage_root": str(storage),
        "relationship_map_file": str(run_path / "relationship-map.json"),
        "project_instructions_file": str(project_instructions),
        "conversation_start_file": str(conversation_start),
        "upload_manifest": prepared["upload_manifest"],
        "source_bundle": str(Path(prepared["bundle"]["bundle_path"]).resolve()),
        "upload_target": upload_target,
        "next_step": "Review upload-manifest.json, manually upload files to the configured ChatGPT Project path, then import returned artifacts.",
    }


def simulate_web_response(*, demo_root: str | Path | None = None, run_id: str) -> JSON:
    run_id = _run_id(run_id)
    run_path = _run_dir(demo_root, run_id)
    mapping = _load_mapping(run_path)
    storage = Path(str(mapping["local_authority"]["storage_root"]))
    raw_response = storage / run_id / "raw-response.txt"
    plan = {
        "packet_type": "codex_execution_plan",
        "run_id": run_id,
        "task_id": TASK_ID,
        "created_by": "chatgpt_web",
        "language": "en",
        "dispatch_strategy": "serial_then_parallel",
        "local_supervisor": "codex_main_thread",
        "execution_units": [
            {
                "id": "design",
                "title": "Confirm the demo change boundary",
                "dispatch_mode": "serial",
                "prompt": "Confirm the target behavior and acceptance criteria before drafting code changes.",
                "owned_paths": ["demo_module.py"],
                "depends_on": [],
                "expected_artifacts": ["report.md"],
            },
            {
                "id": "implementation",
                "title": "Draft the demo patch",
                "dispatch_mode": "serial",
                "prompt": "Draft a unified diff that changes demo_module.greeting from old to new.",
                "owned_paths": ["demo_module.py"],
                "depends_on": ["design"],
                "expected_artifacts": ["changes.patch", "testing-guide.md"],
            },
        ],
        "acceptance_checks": [["python", "-m", "unittest", "test_demo_module"]],
    }
    raw_text = f"""ARTIFACT: codex-execution-plan.json
{json.dumps(plan, ensure_ascii=False, indent=2)}

ARTIFACT: report.md
# Demo Report

Candidate patch drafted as if it came from ChatGPT Web. No local tests were run inside ChatGPT Web.

ARTIFACT: changes.patch
diff --git a/demo_module.py b/demo_module.py
--- a/demo_module.py
+++ b/demo_module.py
@@ -1,2 +1,2 @@
 def greeting() -> str:
-    return "old"
+    return "new"

ARTIFACT: testing-guide.md
# Testing Guide

Local Codex should run `python -m unittest test_demo_module` from the demo workspace after applying `changes.patch`. The expected result is one passing test for `DemoModuleTests.test_greeting`.

LIMITATIONS:
- No local tests were run inside ChatGPT Web.
"""
    _write_text(raw_response, raw_text)
    mapping["status"] = "simulated_web_response_ready"
    mapping["safe_artifacts"]["raw_response_file"] = str(raw_response)
    mapping["updated_at"] = now_iso()
    _write_mapping(run_path, mapping)
    return {
        "ok": True,
        "run_id": run_id,
        "raw_response_file": str(raw_response),
        "relationship_map_file": str(run_path / "relationship-map.json"),
        "next_step": "Run complete-demo to import the response, apply the patch locally, and write a supervisor receipt.",
    }


def complete_demo(*, demo_root: str | Path | None = None, run_id: str) -> JSON:
    run_id = _run_id(run_id)
    run_path = _run_dir(demo_root, run_id)
    mapping = _load_mapping(run_path)
    storage = Path(str(mapping["local_authority"]["storage_root"]))
    workspace = Path(str(mapping["local_authority"]["workspace_root"]))
    raw_response = storage / run_id / "raw-response.txt"
    if not raw_response.exists():
        raise AssistError(f"missing raw response: {raw_response}")

    imported = import_web_run(run_id=run_id, raw_text_file=raw_response, storage=storage)
    response_dir = workspace / ".tmp" / "chatgpt-web" / run_id / "response"
    execution_plan = load_execution_plan_from_response(response_dir, expected_run_id=run_id)
    dispatch_receipt = dispatch_execution_plan(
        execution_plan,
        workspace_root=workspace,
        response_dir=response_dir,
    )
    receipt = apply_web_run(
        run_id=run_id,
        storage=storage,
        checks=[
            [
                sys.executable,
                "-m",
                "unittest",
                "test_demo_module",
            ]
        ],
    )
    receipt_file = workspace / ".tmp" / "chatgpt-web" / run_id / "local-supervisor-receipt.json"
    dispatch_receipt_file = workspace / ".tmp" / "chatgpt-web" / run_id / "codex-dispatch-receipt.json"
    mapping["status"] = (
        "accepted_by_local_supervisor" if receipt.get("local_gate_status") == "passed" else "rejected_by_local_supervisor"
    )
    mapping["safe_artifacts"]["response_dir"] = str(workspace / ".tmp" / "chatgpt-web" / run_id / "response")
    mapping["safe_artifacts"]["receipt_file"] = str(receipt_file)
    mapping["safe_artifacts"]["dispatch_receipt_file"] = str(dispatch_receipt_file)
    mapping["local_receipt_summary"] = {
        "local_gate_status": receipt.get("local_gate_status"),
        "check_count": len(receipt.get("checks", [])),
        "rolled_back": bool(receipt.get("rolled_back", False)),
    }
    mapping["dispatch_receipt_summary"] = {
        "local_gate_status": dispatch_receipt.get("local_gate_status"),
        "batch_count": len(dispatch_receipt.get("dispatch_batches", [])),
        "unit_count": len(dispatch_receipt.get("unit_receipts", [])),
    }
    mapping["updated_at"] = now_iso()
    _write_mapping(run_path, mapping)
    return {
        "ok": receipt.get("local_gate_status") == "passed",
        "run_id": run_id,
        "imported": imported,
        "dispatch_receipt_file": str(dispatch_receipt_file),
        "dispatch_gate_status": dispatch_receipt.get("local_gate_status"),
        "local_gate_status": receipt.get("local_gate_status"),
        "receipt_file": str(receipt_file),
        "relationship_map_file": str(run_path / "relationship-map.json"),
        "workspace_root": str(workspace),
    }


def _fake_codex_cli_script() -> str:
    return """import json
import pathlib
import sys

args = sys.argv[1:]
last_message = pathlib.Path(args[args.index("--output-last-message") + 1])
last_message.parent.mkdir(parents=True, exist_ok=True)
last_message.write_text("Fake Codex agent completed the demo dispatch unit.\\n", encoding="utf-8")
print(json.dumps({"event": "fake_codex_agent_completed", "args": args}))
"""


def dispatch_demo_with_fake_codex(*, demo_root: str | Path | None = None, run_id: str) -> JSON:
    run_id = _run_id(run_id)
    run_path = _run_dir(demo_root, run_id)
    mapping = _load_mapping(run_path)
    workspace = Path(str(mapping["local_authority"]["workspace_root"]))
    response_dir = workspace / ".tmp" / "chatgpt-web" / run_id / "response"
    if not (response_dir / "codex-execution-plan.json").exists():
        raise AssistError(f"missing imported codex execution plan: {response_dir / 'codex-execution-plan.json'}")

    fake_codex = run_path / "fake-codex-cli.py"
    _write_text(fake_codex, _fake_codex_cli_script())
    execution_plan = load_execution_plan_from_response(response_dir, expected_run_id=run_id)
    from chatgpt_web_execution_dispatcher import build_codex_cli_backend

    backend = build_codex_cli_backend(
        codex_command=[sys.executable, str(fake_codex)],
        sandbox="workspace-write",
    )
    dispatch_receipt = dispatch_execution_plan(
        execution_plan,
        workspace_root=workspace,
        response_dir=response_dir,
        dispatch_backend=backend,
    )
    dispatch_receipt_file = workspace / ".tmp" / "chatgpt-web" / run_id / "codex-dispatch-receipt.json"
    mapping["status"] = "fake_codex_cli_dispatched"
    mapping["safe_artifacts"]["fake_codex_cli_file"] = str(fake_codex)
    mapping["safe_artifacts"]["dispatch_receipt_file"] = str(dispatch_receipt_file)
    mapping["dispatch_receipt_summary"] = {
        "local_gate_status": dispatch_receipt.get("local_gate_status"),
        "backend": "codex_cli",
        "unit_count": len(dispatch_receipt.get("unit_receipts", [])),
    }
    mapping["updated_at"] = now_iso()
    _write_mapping(run_path, mapping)
    return {
        "ok": dispatch_receipt.get("local_gate_status") == "dispatched",
        "run_id": run_id,
        "dispatch_gate_status": dispatch_receipt.get("local_gate_status"),
        "dispatch_receipt_file": str(dispatch_receipt_file),
        "fake_codex_cli_file": str(fake_codex),
        "relationship_map_file": str(run_path / "relationship-map.json"),
    }


def run_demo(
    *,
    demo_root: str | Path | None = None,
    run_id: str | None = None,
    codex_thread_ref: str = "codex-thread-local-demo",
    chatgpt_project_alias: str = DEFAULT_CHATGPT_PROJECT_ALIAS,
    chatgpt_conversation_alias: str = "demo-conversation-001",
    upload_target: str = DEFAULT_UPLOAD_TARGET,
    force: bool = False,
) -> JSON:
    prepared = prepare_demo(
        demo_root=demo_root,
        run_id=run_id,
        codex_thread_ref=codex_thread_ref,
        chatgpt_project_alias=chatgpt_project_alias,
        chatgpt_conversation_alias=chatgpt_conversation_alias,
        upload_target=upload_target,
        force=force,
    )
    simulated = simulate_web_response(demo_root=demo_root, run_id=prepared["run_id"])
    completed = complete_demo(demo_root=demo_root, run_id=prepared["run_id"])
    return {
        "ok": bool(completed["ok"]),
        "run_id": prepared["run_id"],
        "prepared": prepared,
        "simulated": simulated,
        "completed": completed,
    }


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--demo-root", type=Path)
    parser.add_argument("--run-id")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare-demo", help="Create demo workspace, safe upload bundle, and relationship map")
    _add_common_args(prepare_parser)
    prepare_parser.add_argument("--codex-thread-ref", default="codex-thread-local-demo")
    prepare_parser.add_argument("--chatgpt-project-alias", default=DEFAULT_CHATGPT_PROJECT_ALIAS)
    prepare_parser.add_argument("--chatgpt-conversation-alias", default="demo-conversation-001")
    prepare_parser.add_argument("--upload-target", choices=sorted(UPLOAD_TARGETS), default=DEFAULT_UPLOAD_TARGET)
    prepare_parser.add_argument("--force", action="store_true")

    simulate_parser = subparsers.add_parser("simulate-web-response", help="Write a local mock ARTIFACT response for offline demo")
    _add_common_args(simulate_parser)

    dispatch_parser = subparsers.add_parser("dispatch-fake-codex", help="Dispatch imported execution plan through a fake Codex CLI backend")
    _add_common_args(dispatch_parser)

    complete_parser = subparsers.add_parser("complete-demo", help="Import response, apply patch locally, and write supervisor receipt")
    _add_common_args(complete_parser)

    run_parser = subparsers.add_parser("run-demo", help="Run prepare, simulated response, and local verification")
    _add_common_args(run_parser)
    run_parser.add_argument("--codex-thread-ref", default="codex-thread-local-demo")
    run_parser.add_argument("--chatgpt-project-alias", default=DEFAULT_CHATGPT_PROJECT_ALIAS)
    run_parser.add_argument("--chatgpt-conversation-alias", default="demo-conversation-001")
    run_parser.add_argument("--upload-target", choices=sorted(UPLOAD_TARGETS), default=DEFAULT_UPLOAD_TARGET)
    run_parser.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-demo":
            result = prepare_demo(
                demo_root=args.demo_root,
                run_id=args.run_id,
                codex_thread_ref=args.codex_thread_ref,
                chatgpt_project_alias=args.chatgpt_project_alias,
                chatgpt_conversation_alias=args.chatgpt_conversation_alias,
                upload_target=args.upload_target,
                force=args.force,
            )
        elif args.command == "simulate-web-response":
            result = simulate_web_response(demo_root=args.demo_root, run_id=args.run_id)
        elif args.command == "dispatch-fake-codex":
            result = dispatch_demo_with_fake_codex(demo_root=args.demo_root, run_id=args.run_id)
        elif args.command == "complete-demo":
            result = complete_demo(demo_root=args.demo_root, run_id=args.run_id)
        elif args.command == "run-demo":
            result = run_demo(
                demo_root=args.demo_root,
                run_id=args.run_id,
                codex_thread_ref=args.codex_thread_ref,
                chatgpt_project_alias=args.chatgpt_project_alias,
                chatgpt_conversation_alias=args.chatgpt_conversation_alias,
                upload_target=args.upload_target,
                force=args.force,
            )
        else:
            raise AssistError(f"unknown command: {args.command}")
    except (AssistError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
