#!/usr/bin/env python3
"""Local Codex supervisor for ChatGPT App no-API assist runs.

This script validates candidate artifacts produced through the no-API connector
and records a local supervisor receipt. It is the only component in this flow
that runs local checks. It does not call OpenAI APIs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from chatgpt_app_no_api_common import (
    AssistError,
    CHANNEL,
    now_iso,
    relative_to_root,
    storage_root as resolve_storage_root,
    validate_artifact_manifest,
    write_json_file,
)


JSON = dict[str, Any]


def run_check(command: list[str], cwd: Path) -> JSON:
    if not command:
        raise AssistError("check command must not be empty")
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip()
    return {
        "name": " ".join(command),
        "level": "local",
        "status": "passed" if completed.returncode == 0 else "failed",
        "command": command,
        "exit_code": completed.returncode,
        "output_tail": output[-4000:],
    }


def supervise_run(
    *,
    run_id: str,
    storage_root: str | Path | None = None,
    check_commands: list[list[str]] | None = None,
) -> JSON:
    root = resolve_storage_root(storage_root)
    checked = validate_artifact_manifest(run_id, root)
    run_path = root / run_id
    checks: list[JSON] = []
    for command in check_commands or []:
        checks.append(run_check(command, cwd=root))

    artifact_status = "passed"
    checks_status = "passed"
    if not checked["artifacts"]:
        artifact_status = "failed"
    if checks and any(check["status"] != "passed" or check["exit_code"] != 0 for check in checks):
        checks_status = "failed"

    status = "passed" if artifact_status == "passed" and checks_status == "passed" else "failed"
    if not checks:
        status = "needs_manual_review"

    receipt = {
        "packet_type": "local_supervisor_receipt",
        "channel": CHANNEL,
        "run_id": run_id,
        "created_at": now_iso(),
        "status": status,
        "local_gate_status": status,
        "request_goal": checked["request"].get("goal"),
        "accepted_artifacts": checked["artifacts"] if status == "passed" else [],
        "candidate_artifacts": checked["artifacts"],
        "checks": checks,
        "known_risks": [] if status == "passed" else ["Candidate artifacts require revision or manual review."],
        "api_model_calls_used": False,
        "supervisor": "local_codex",
    }
    write_json_file(run_path / "local-supervisor-receipt.json", receipt)
    if status != "passed":
        write_json_file(
            run_path / "supervisor-feedback.json",
            {
                "run_id": run_id,
                "created_at": receipt["created_at"],
                "status": status,
                "message": "Local supervisor did not pass this candidate run.",
                "checks": checks,
                "candidate_artifacts": checked["artifacts"],
            },
        )
    return receipt


def parse_check_args(values: list[str] | None) -> list[list[str]]:
    commands: list[list[str]] = []
    for value in values or []:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AssistError(f"--check must be a JSON array of command argv: {value}") from exc
        if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
            raise AssistError("--check must be a JSON array of strings")
        commands.append(parsed)
    return commands


def parse_check_files(values: list[Path] | None) -> list[list[str]]:
    commands: list[list[str]] = []
    for path in values or []:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise AssistError(f"--check-json-file must contain a JSON array of command argv: {path}") from exc
        if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
            raise AssistError("--check-json-file must contain a JSON array of strings")
        commands.append(parsed)
    return commands


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ChatGPT App no-API artifacts and write a local supervisor receipt.")
    parser.add_argument("run_id")
    parser.add_argument("--storage-root", type=Path, default=None)
    parser.add_argument(
        "--check",
        action="append",
        help='Local check command as JSON argv, e.g. --check "[\\"python\\", \\"-m\\", \\"unittest\\"]"',
    )
    parser.add_argument(
        "--check-json-file",
        action="append",
        type=Path,
        help="Path to a JSON file containing one local check command argv array.",
    )
    parser.add_argument("--json", action="store_true", help="Print full receipt JSON")
    args = parser.parse_args(argv)

    try:
        receipt = supervise_run(
            run_id=args.run_id,
            storage_root=args.storage_root,
            check_commands=parse_check_args(args.check) + parse_check_files(args.check_json_file),
        )
    except AssistError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']}: {relative_to_root(resolve_storage_root(args.storage_root) / args.run_id / 'local-supervisor-receipt.json')}")
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
