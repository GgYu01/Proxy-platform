#!/usr/bin/env python3
"""Import ChatGPT Web manual-assist artifacts into the local workspace.

This tool is for the no-tunnel Simprint ChatGPT Web workflow. It parses copied
ChatGPT output with ``ARTIFACT: <filename>`` markers, writes the returned files
under ``.tmp/chatgpt-web/.../response/``, generates ``response.json``, and can
copy accepted artifacts to a project or user-level destination after a passed
local supervisor receipt exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from chatgpt_app_no_api_common import AssistError, reject_secret_text
from validate_chatgpt_web_manual_assist import detect_and_validate


ROOT = Path(__file__).resolve().parents[1]
CHANNEL = "chatgpt_web_manual"
PRODUCER = "chatgpt_web"
ARTIFACT_MARKER_RE = re.compile(r"(?im)^ARTIFACT:\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._/-]{0,240})\s*$")
TRAILING_SECTION_RE = re.compile(r"(?im)^(?:LIMITATIONS|SUGGESTED_LOCAL_CHECKS|NOTES|REPAIR_INSTRUCTIONS):\s*$")
ALLOWED_EXTENSIONS = {".diff", ".html", ".json", ".md", ".patch", ".txt"}
TYPE_BY_EXTENSION = {
    ".diff": "patch",
    ".html": "html_report",
    ".json": "json",
    ".md": "markdown_report",
    ".patch": "patch",
    ".txt": "text_report",
}
MAX_ARTIFACT_BYTES = 2_000_000
PATCH_PATH_RE = re.compile(r"^diff --git a/(?P<old>.+?) b/(?P<new>.+?)\s*$")
IGNORED_DIRTY_PREFIXES = (".tmp/", "tmp/", "__pycache__/", ".pytest_cache/")


JSON = dict[str, Any]


class ImportError(AssistError):
    """Raised when ChatGPT Web artifact import is invalid."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def relative_to_workspace(path: Path, workspace_root: Path) -> str:
    try:
        return path.resolve().relative_to(workspace_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _safe_filename(name: str) -> str:
    if "/" in name or "\\" in name or ".." in name:
        raise ImportError("artifact filename must be a plain file name")
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ImportError(f"artifact extension is not allowed: {Path(name).suffix}")
    return name


def _safe_files_artifact_target(name: str) -> str:
    normalized = name.replace("\\", "/")
    if not normalized.startswith("files/"):
        raise ImportError("artifact path must be a plain file name or files/<relative-path>")
    target = normalized[len("files/") :]
    pure = PurePosixPath(target)
    forbidden_parts = {".git", ".tmp", "tmp", "__pycache__", ".pytest_cache"}
    if (
        not target
        or pure.is_absolute()
        or re.match(r"^[A-Za-z]:", target)
        or any(part in {"", ".", ".."} for part in pure.parts)
        or any(part in forbidden_parts for part in pure.parts)
    ):
        raise ImportError("files artifact target must be a safe non-temporary relative path")
    if Path(target).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ImportError(f"artifact extension is not allowed: {Path(target).suffix}")
    return pure.as_posix()


def _safe_artifact_reference(name: str) -> JSON:
    normalized = name.strip().replace("\\", "/")
    if normalized.startswith("files/"):
        target_path = _safe_files_artifact_target(normalized)
        return {
            "marker_name": normalized,
            "staged_relative_path": normalized,
            "target_path": target_path,
            "delivery_mode": "full_file_candidate",
        }
    plain = _safe_filename(normalized)
    return {
        "marker_name": plain,
        "staged_relative_path": plain,
        "target_path": None,
        "delivery_mode": "artifact",
    }


def _artifact_type_for_filename(path: Path) -> str:
    if path.name == "codex-execution-plan.json":
        return "execution_plan"
    return TYPE_BY_EXTENSION.get(path.suffix.lower(), "text_report")


def _require_inside_workspace(path: Path, workspace_root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise ImportError(f"{label} must stay inside the workspace") from exc
    return resolved


def _require_ignored_workspace_path(path: Path, workspace_root: Path, label: str) -> Path:
    resolved = _require_inside_workspace(path, workspace_root, label)
    relative = resolved.relative_to(workspace_root.resolve()).as_posix()
    if not (relative.startswith(".tmp/") or relative.startswith("tmp/")):
        raise ImportError(f"{label} must be under .tmp/ or tmp/")
    return resolved


def parse_artifact_blocks(raw_text: str) -> list[JSON]:
    reject_secret_text(raw_text, "raw ChatGPT Web response")
    matches = list(ARTIFACT_MARKER_RE.finditer(raw_text))
    if not matches:
        raise ImportError("no ARTIFACT blocks found")

    artifacts: list[JSON] = []
    for index, match in enumerate(matches):
        reference = _safe_artifact_reference(match.group("name").strip())
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        content = raw_text[start:end].lstrip("\r\n")
        if index + 1 == len(matches):
            trailing = TRAILING_SECTION_RE.search(content)
            if trailing:
                content = content[: trailing.start()]
        if not content.strip():
            raise ImportError(f"artifact is empty: {reference['marker_name']}")
        encoded_size = len(content.encode("utf-8"))
        if encoded_size > MAX_ARTIFACT_BYTES:
            raise ImportError(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes: {reference['marker_name']}")
        reject_secret_text(content, f"artifact {reference['marker_name']}")
        artifacts.append({**reference, "content": content})
    return artifacts


def _response_packet_id(run_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id).strip("-") or "run"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"cgw_resp_{safe}_{stamp}"


def import_chatgpt_response(
    *,
    raw_text: str,
    workspace_root: str | Path | None = None,
    response_dir: str | Path,
    request_packet_id: str,
    task_id: str,
    run_id: str,
    response_packet_id: str | None = None,
) -> JSON:
    workspace = Path(workspace_root or ROOT).resolve()
    destination = _require_ignored_workspace_path(Path(response_dir), workspace, "response_dir")
    destination.mkdir(parents=True, exist_ok=True)
    artifacts: list[JSON] = []

    for artifact in parse_artifact_blocks(raw_text):
        content = str(artifact["content"])
        artifact_path = destination / Path(*PurePosixPath(str(artifact["staged_relative_path"])).parts)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with artifact_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        record = {
            "name": str(artifact["marker_name"]),
            "path": relative_to_workspace(artifact_path, workspace),
            "sha256": sha256_text(content),
            "type": _artifact_type_for_filename(artifact_path),
            "delivery_mode": str(artifact["delivery_mode"]),
        }
        if artifact.get("target_path"):
            record["target_path"] = str(artifact["target_path"])
        artifacts.append(record)

    packet_id = response_packet_id or _response_packet_id(run_id)
    packet = {
        "packet_type": "chatgpt_web_response",
        "packet_id": packet_id,
        "request_packet_id": request_packet_id,
        "task_id": task_id,
        "run_id": run_id,
        "channel": CHANNEL,
        "producer": PRODUCER,
        "artifacts": artifacts,
        "self_reported_verification": [
            "ChatGPT Web produced candidate artifacts only; no local checks were run in ChatGPT Web."
        ],
        "limitations": [
            "No local tests were run inside ChatGPT Web.",
            "Local Codex supervisor must validate and decide whether to accept these artifacts.",
        ],
    }
    detect_and_validate(packet)
    response_json = destination / "response.json"
    response_json.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "response_packet_id": packet_id,
        "response_json": relative_to_workspace(response_json, workspace),
        "response_dir": relative_to_workspace(destination, workspace),
        "artifact_count": len(artifacts),
        "artifacts": [artifact["path"] for artifact in artifacts],
    }


def _load_json(path: Path) -> JSON:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ImportError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ImportError(f"invalid JSON file: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ImportError(f"JSON root must be an object: {path}")
    return payload


def _run_check(command: list[str], cwd: Path) -> JSON:
    if not command:
        raise ImportError("check command must not be empty")
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
        "level": "L1",
        "status": "passed" if completed.returncode == 0 else "failed",
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "log_uri": "",
        "output_tail": output[-4000:],
    }


def _run_command(command: list[str], cwd: Path, *, name: str, level: str = "L1") -> JSON:
    if not command:
        raise ImportError("command must not be empty")
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
        "name": name,
        "level": level,
        "status": "passed" if completed.returncode == 0 else "failed",
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "log_uri": "",
        "output_tail": output[-4000:],
    }


def _successful(command: list[str], cwd: Path, *, name: str, level: str = "L1") -> JSON:
    result = _run_command(command, cwd, name=name, level=level)
    if result["status"] != "passed":
        raise ImportError(f"{name} failed: {result.get('output_tail', '')}")
    return result


def _safe_worktree_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", value)
        or ".." in parts
        or "" in parts
        or normalized.startswith(".git/")
        or normalized.startswith(".tmp/")
        or normalized.startswith("tmp/")
    ):
        raise ImportError(f"{label} must be a safe non-temporary relative path")
    return normalized


def _worktree_paths_from_patch(patch_path: Path) -> list[str]:
    paths: list[str] = []
    for line in patch_path.read_text(encoding="utf-8").splitlines():
        match = PATCH_PATH_RE.match(line)
        if not match:
            continue
        old_path = match.group("old")
        new_path = match.group("new")
        for candidate in (new_path, old_path):
            if candidate != "/dev/null":
                paths.append(_safe_worktree_path(candidate, f"patch path in {patch_path.name}"))
                break
    return sorted(set(paths))


def _git_output(command: list[str], cwd: Path) -> str:
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
        raise ImportError(f"git command failed: {' '.join(command)}\n{output}")
    return completed.stdout


def _git_changed_paths(workspace: Path) -> set[str]:
    output = _git_output(["git", "status", "--porcelain=v1", "-z"], workspace)
    paths: set[str] = set()
    entries = [entry for entry in output.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        status = entry[:2]
        path = entry[3:]
        if status.startswith("R") or status.startswith("C"):
            normalized = path.replace("\\", "/")
            if not normalized.startswith(IGNORED_DIRTY_PREFIXES):
                paths.add(normalized)
            index += 2
            continue
        normalized = path.replace("\\", "/")
        if not normalized.startswith(IGNORED_DIRTY_PREFIXES):
            paths.add(normalized)
        index += 1
    return paths


def _load_passed_receipt(receipt_path: Path, workspace: Path) -> JSON:
    receipt_file = _require_ignored_workspace_path(receipt_path, workspace, "receipt_path")
    receipt = _load_json(receipt_file)
    detect_and_validate(receipt)
    if receipt.get("local_gate_status") != "passed":
        raise ImportError("local supervisor receipt must be passed before delivery actions")
    return receipt


def _receipt_check_entry(check: JSON) -> JSON:
    return {
        "name": check["name"],
        "level": check["level"],
        "status": check["status"],
        "command": check["command"],
        "exit_code": check["exit_code"],
        "log_uri": check.get("log_uri", ""),
    }


def supervise_response(
    *,
    workspace_root: str | Path | None = None,
    response_dir: str | Path,
    check_commands: list[list[str]] | None = None,
    receipt_path: str | Path | None = None,
) -> JSON:
    workspace = Path(workspace_root or ROOT).resolve()
    source_dir = _require_ignored_workspace_path(Path(response_dir), workspace, "response_dir")
    response_packet = _load_json(source_dir / "response.json")
    detect_and_validate(response_packet)
    checks = [_run_check(command, workspace) for command in check_commands or []]
    all_passed = bool(checks) and all(check["status"] == "passed" and check["exit_code"] == 0 for check in checks)
    local_gate_status = "passed" if all_passed else "failed"
    accepted = [artifact["path"] for artifact in response_packet["artifacts"]] if all_passed else []
    receipt = {
        "packet_type": "local_supervisor_receipt",
        "packet_id": f"cgw_receipt_{response_packet['run_id']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "request_packet_id": response_packet["request_packet_id"],
        "response_packet_id": response_packet["packet_id"],
        "task_id": response_packet["task_id"],
        "run_id": response_packet["run_id"],
        "local_gate_status": local_gate_status,
        "checks": [_receipt_check_entry(check) for check in checks],
        "accepted_artifacts": accepted,
        "known_risks": [] if all_passed else ["Local supervisor checks failed or were not provided."],
    }
    detect_and_validate(receipt)
    target_receipt = (
        _require_ignored_workspace_path(Path(receipt_path), workspace, "receipt_path")
        if receipt_path
        else source_dir.parent / "local-supervisor-receipt.json"
    )
    target_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **receipt,
        "receipt_path": relative_to_workspace(target_receipt, workspace),
        "check_outputs": checks,
    }


def _response_artifact_paths(response_packet: JSON, workspace: Path, source_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for artifact in response_packet["artifacts"]:
        artifact_path = workspace / str(artifact["path"])
        if not artifact_path.exists():
            artifact_path = source_dir / Path(*PurePosixPath(str(artifact["path"]).split("response/", 1)[-1]).parts)
        paths.append(_require_ignored_workspace_path(artifact_path, workspace, "artifact path"))
    return paths


def _patch_artifact_paths(response_packet: JSON, workspace: Path, source_dir: Path) -> list[Path]:
    patches: list[Path] = []
    for artifact in response_packet["artifacts"]:
        artifact_type = str(artifact.get("type", ""))
        artifact_path = workspace / str(artifact["path"])
        if not artifact_path.exists():
            artifact_path = source_dir / Path(*PurePosixPath(str(artifact["path"]).split("response/", 1)[-1]).parts)
        path = _require_ignored_workspace_path(artifact_path, workspace, "patch artifact path")
        if artifact_type == "patch" or path.suffix.lower() in {".patch", ".diff"}:
            reject_secret_text(path.read_text(encoding="utf-8"), f"patch artifact {path.name}")
            patches.append(path)
    return patches


def apply_response_patches(
    *,
    workspace_root: str | Path | None = None,
    response_dir: str | Path,
    check_commands: list[list[str]] | None = None,
    receipt_path: str | Path | None = None,
    keep_failed: bool = False,
) -> JSON:
    workspace = Path(workspace_root or ROOT).resolve()
    source_dir = _require_ignored_workspace_path(Path(response_dir), workspace, "response_dir")
    response_packet = _load_json(source_dir / "response.json")
    detect_and_validate(response_packet)
    patch_paths = _patch_artifact_paths(response_packet, workspace, source_dir)
    artifact_paths = [relative_to_workspace(path, workspace) for path in _response_artifact_paths(response_packet, workspace, source_dir)]
    accepted_worktree_paths = sorted({path for patch_path in patch_paths for path in _worktree_paths_from_patch(patch_path)})

    checks: list[JSON] = []
    applied: list[Path] = []
    rolled_back = False
    if not patch_paths:
        checks.append(
            {
                "name": "patch artifacts present",
                "level": "L1",
                "status": "failed",
                "command": "inspect response.json",
                "exit_code": 1,
                "log_uri": "",
                "output_tail": "No .patch or .diff artifact was returned by ChatGPT Web.",
            }
        )
    for patch_path in patch_paths:
        check = _run_command(["git", "apply", "--check", str(patch_path)], workspace, name=f"git apply --check {patch_path.name}")
        checks.append(check)
        if check["status"] != "passed":
            break
    if checks and all(check["status"] == "passed" and check["exit_code"] == 0 for check in checks):
        for patch_path in patch_paths:
            apply_check = _run_command(["git", "apply", str(patch_path)], workspace, name=f"git apply {patch_path.name}")
            checks.append(apply_check)
            if apply_check["status"] != "passed":
                break
            applied.append(patch_path)
        if all(check["status"] == "passed" and check["exit_code"] == 0 for check in checks):
            for command in check_commands or []:
                checks.append(_run_check(command, workspace))

    all_passed = bool(checks) and all(check["status"] == "passed" and check["exit_code"] == 0 for check in checks)
    if applied and not all_passed and not keep_failed:
        for patch_path in reversed(applied):
            rollback = _run_command(["git", "apply", "-R", str(patch_path)], workspace, name=f"git apply -R {patch_path.name}")
            checks.append(rollback)
            rolled_back = True

    local_gate_status = "passed" if all_passed else "failed"
    receipt = {
        "packet_type": "local_supervisor_receipt",
        "packet_id": f"cgw_receipt_{response_packet['run_id']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "request_packet_id": response_packet["request_packet_id"],
        "response_packet_id": response_packet["packet_id"],
        "task_id": response_packet["task_id"],
        "run_id": response_packet["run_id"],
        "local_gate_status": local_gate_status,
        "checks": [_receipt_check_entry(check) for check in checks],
        "accepted_artifacts": artifact_paths if all_passed else [],
        "accepted_worktree_paths": accepted_worktree_paths if all_passed else [],
        "known_risks": [] if all_passed else ["Patch application or local verification failed.", f"rolled_back={rolled_back}"],
    }
    detect_and_validate(receipt)
    target_receipt = (
        _require_ignored_workspace_path(Path(receipt_path), workspace, "receipt_path")
        if receipt_path
        else source_dir.parent / "local-supervisor-receipt.json"
    )
    target_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **receipt,
        "receipt_path": relative_to_workspace(target_receipt, workspace),
        "patches": [relative_to_workspace(path, workspace) for path in patch_paths],
        "rolled_back": rolled_back,
        "check_outputs": checks,
    }


def publish_accepted_artifacts(
    *,
    workspace_root: str | Path | None = None,
    response_dir: str | Path,
    receipt_path: str | Path,
    destination_dir: str | Path,
) -> JSON:
    workspace = Path(workspace_root or ROOT).resolve()
    source_dir = _require_ignored_workspace_path(Path(response_dir), workspace, "response_dir")
    receipt_file = _require_ignored_workspace_path(Path(receipt_path), workspace, "receipt_path")
    response_packet = _load_json(source_dir / "response.json")
    receipt = _load_json(receipt_file)
    detect_and_validate(response_packet)
    detect_and_validate(receipt)

    if receipt.get("local_gate_status") != "passed":
        raise ImportError("local supervisor receipt must be passed before publishing artifacts")
    if receipt.get("response_packet_id") != response_packet.get("packet_id"):
        raise ImportError("receipt response_packet_id does not match response.json")

    accepted = receipt.get("accepted_artifacts")
    if not isinstance(accepted, list) or not accepted:
        raise ImportError("passed receipt must include accepted_artifacts")
    accepted_paths = {str(path).replace("\\", "/") for path in accepted}

    destination = Path(destination_dir).resolve()
    if not destination.exists():
        destination.mkdir(parents=True)
    copied: list[JSON] = []
    for artifact in response_packet["artifacts"]:
        artifact_path = str(artifact["path"]).replace("\\", "/")
        if artifact_path not in accepted_paths:
            continue
        source = _require_ignored_workspace_path(workspace / artifact_path, workspace, "artifact path")
        target_relative = str(artifact.get("target_path") or source.name)
        if artifact.get("target_path"):
            target_relative = _safe_worktree_path(target_relative, "artifact target_path")
        target = destination / Path(*PurePosixPath(target_relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        reject_secret_text(source.read_text(encoding="utf-8"), f"accepted artifact {source.name}")
        shutil.copy2(source, target)
        copied.append(
            {
                "source": relative_to_workspace(source, workspace),
                "destination": str(target),
                "sha256": artifact["sha256"],
            }
        )

    if not copied:
        raise ImportError("no response artifacts matched accepted_artifacts in the receipt")
    return {
        "ok": True,
        "destination_dir": str(destination),
        "copied": copied,
    }


def commit_accepted_changes(
    *,
    workspace_root: str | Path | None = None,
    receipt_path: str | Path,
    message: str,
    allow_dirty_unaccepted: bool = False,
    push: bool = False,
    remote: str | None = None,
    branch: str | None = None,
) -> JSON:
    workspace = Path(workspace_root or ROOT).resolve()
    reject_secret_text(message, "commit message")
    if not message.strip():
        raise ImportError("commit message must not be empty")
    receipt = _load_passed_receipt(Path(receipt_path), workspace)
    accepted_paths_value = receipt.get("accepted_worktree_paths")
    if not isinstance(accepted_paths_value, list) or not accepted_paths_value:
        raise ImportError("passed receipt must include accepted_worktree_paths before committing")
    accepted_paths = [_safe_worktree_path(str(path), "accepted_worktree_paths[]") for path in accepted_paths_value]

    changed_paths = _git_changed_paths(workspace)
    unaccepted_dirty = sorted(changed_paths - set(accepted_paths))
    if unaccepted_dirty and not allow_dirty_unaccepted:
        raise ImportError(f"unaccepted dirty paths block commit: {unaccepted_dirty}")

    checks: list[JSON] = []
    checks.append(_successful(["git", "add", "--", *accepted_paths], workspace, name="git add accepted worktree paths", level="G0"))
    staged_paths = {
        path.strip().replace("\\", "/")
        for path in _git_output(["git", "diff", "--cached", "--name-only"], workspace).splitlines()
        if path.strip()
    }
    if not staged_paths:
        raise ImportError("no accepted changes are staged for commit")
    unexpected_staged = sorted(staged_paths - set(accepted_paths))
    if unexpected_staged:
        raise ImportError(f"unexpected staged paths block commit: {unexpected_staged}")

    checks.append(_successful(["git", "commit", "-m", message], workspace, name="git commit accepted changes", level="G0"))
    commit_sha = _git_output(["git", "rev-parse", "HEAD"], workspace).strip()
    result: JSON = {
        "ok": True,
        "action": "commit",
        "commit": commit_sha,
        "committed_paths": sorted(staged_paths),
        "unaccepted_dirty_paths": unaccepted_dirty,
        "checks": checks,
    }
    if push:
        push_command = ["git", "push"]
        if remote or branch:
            if not remote or not branch:
                raise ImportError("push requires both remote and branch when either is provided")
            reject_secret_text(remote, "git remote")
            reject_secret_text(branch, "git branch")
            push_command.extend([remote, branch])
        checks.append(_successful(push_command, workspace, name="git push accepted commit", level="G0"))
        result["action"] = "commit_and_push"
        result["pushed"] = True
        result["push_remote"] = remote
        result["push_branch"] = branch
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-response", help="Parse ARTIFACT blocks and write response.json")
    import_parser.add_argument("--raw-text-file", required=True, type=Path)
    import_parser.add_argument("--response-dir", required=True, type=Path)
    import_parser.add_argument("--request-packet-id", required=True)
    import_parser.add_argument("--task-id", required=True)
    import_parser.add_argument("--run-id", required=True)
    import_parser.add_argument("--response-packet-id")

    supervise_parser = subparsers.add_parser("supervise-response", help="Run local checks and write local-supervisor-receipt.json")
    supervise_parser.add_argument("--response-dir", required=True, type=Path)
    supervise_parser.add_argument("--receipt", type=Path)
    supervise_parser.add_argument(
        "--check",
        action="append",
        help='Local check command as JSON argv, e.g. --check "[\\"python\\", \\"-m\\", \\"unittest\\"]"',
    )
    supervise_parser.add_argument(
        "--check-json-file",
        action="append",
        type=Path,
        help="Path to a JSON file containing one local check command argv array.",
    )

    publish_parser = subparsers.add_parser("publish-accepted", help="Copy artifacts accepted by a passed receipt")
    publish_parser.add_argument("--response-dir", required=True, type=Path)
    publish_parser.add_argument("--receipt", required=True, type=Path)
    publish_parser.add_argument("--destination-dir", required=True, type=Path)

    apply_parser = subparsers.add_parser("apply-response-patches", help="Apply ChatGPT Web patch artifacts, run checks, and write a receipt")
    apply_parser.add_argument("--response-dir", required=True, type=Path)
    apply_parser.add_argument("--receipt", type=Path)
    apply_parser.add_argument("--keep-failed", action="store_true", help="Keep applied patch changes when verification fails")
    apply_parser.add_argument(
        "--check",
        action="append",
        help='Local check command as JSON argv, e.g. --check "[\\"python\\", \\"-m\\", \\"unittest\\"]"',
    )
    apply_parser.add_argument(
        "--check-json-file",
        action="append",
        type=Path,
        help="Path to a JSON file containing one local check command argv array.",
    )

    commit_parser = subparsers.add_parser("commit-accepted", help="Commit only receipt-approved worktree paths after local supervisor gate passes")
    commit_parser.add_argument("--receipt", required=True, type=Path)
    commit_parser.add_argument("--message", required=True)
    commit_parser.add_argument("--allow-dirty-unaccepted", action="store_true")
    commit_parser.add_argument("--push", action="store_true")
    commit_parser.add_argument("--remote")
    commit_parser.add_argument("--branch")

    args = parser.parse_args(argv)
    try:
        if args.command == "import-response":
            result = import_chatgpt_response(
                raw_text=args.raw_text_file.read_text(encoding="utf-8-sig"),
                workspace_root=args.workspace_root,
                response_dir=args.response_dir,
                request_packet_id=args.request_packet_id,
                task_id=args.task_id,
                run_id=args.run_id,
                response_packet_id=args.response_packet_id,
            )
        elif args.command == "supervise-response":
            checks = []
            for value in args.check or []:
                parsed = json.loads(value)
                if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
                    raise ImportError("--check must be a JSON array of strings")
                checks.append(parsed)
            for path in args.check_json_file or []:
                parsed = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
                    raise ImportError("--check-json-file must contain a JSON array of strings")
                checks.append(parsed)
            result = supervise_response(
                workspace_root=args.workspace_root,
                response_dir=args.response_dir,
                receipt_path=args.receipt,
                check_commands=checks,
            )
        elif args.command == "publish-accepted":
            result = publish_accepted_artifacts(
                workspace_root=args.workspace_root,
                response_dir=args.response_dir,
                receipt_path=args.receipt,
                destination_dir=args.destination_dir,
            )
        elif args.command == "apply-response-patches":
            checks = []
            for value in args.check or []:
                parsed = json.loads(value)
                if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
                    raise ImportError("--check must be a JSON array of strings")
                checks.append(parsed)
            for path in args.check_json_file or []:
                parsed = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
                    raise ImportError("--check-json-file must contain a JSON array of strings")
                checks.append(parsed)
            result = apply_response_patches(
                workspace_root=args.workspace_root,
                response_dir=args.response_dir,
                receipt_path=args.receipt,
                check_commands=checks,
                keep_failed=args.keep_failed,
            )
        elif args.command == "commit-accepted":
            result = commit_accepted_changes(
                workspace_root=args.workspace_root,
                receipt_path=args.receipt,
                message=args.message,
                allow_dirty_unaccepted=args.allow_dirty_unaccepted,
                push=args.push,
                remote=args.remote,
                branch=args.branch,
            )
        else:
            raise ImportError(f"unknown command: {args.command}")
    except (OSError, AssistError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
