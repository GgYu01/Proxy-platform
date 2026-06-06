#!/usr/bin/env python3
"""Shared storage and validation helpers for ChatGPT App no-API assist.

This module intentionally does not call OpenAI APIs. ChatGPT Web supplies model
work through Apps SDK / MCP tool calls; the local filesystem is only an
artifact inbox for Codex supervisor review.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORAGE_ROOT = ROOT / ".tmp" / "chatgpt-app"
WORKSPACE_REGISTRY_FILE = "workspace-registry.json"

CHANNEL = "chatgpt_app_no_api"
PRODUCER = "chatgpt_web_app_connector"

ALLOWED_ARTIFACT_TYPES = {
    "patch",
    "markdown_report",
    "text_report",
    "json",
    "execution_plan",
    "review_notes",
    "code_bundle_manifest",
}

ALLOWED_WORKSPACE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".cjs",
    ".cmake",
    ".cpp",
    ".cs",
    ".css",
    ".diff",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".less",
    ".mjs",
    ".md",
    ".patch",
    ".ps1",
    ".py",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

STRUCTURE_PLACEHOLDER_FILENAMES = {".gitkeep", ".keep"}

DEFAULT_WORKSPACE_EXCLUDE_PATTERNS = {
    ".cache/**",
    ".codex/**",
    ".env",
    ".env.*",
    ".git/**",
    ".gstack/**",
    ".hg/**",
    ".pytest_cache/**",
    ".svn/**",
    ".tmp/**",
    "__pycache__/**",
    "build/**",
    "coverage/**",
    "dist/**",
    "node_modules/**",
    "out/**",
    "secrets/**",
    "tmp/**",
    "venv/**",
    ".venv/**",
}

FORBIDDEN_WORKSPACE_PATH_PARTS = {
    ".cache",
    ".codex",
    ".git",
    ".gstack",
    ".hg",
    ".pytest_cache",
    ".svn",
    ".tmp",
    "__pycache__",
    "node_modules",
    "secrets",
    "tmp",
    "venv",
    ".venv",
}

ALLOWED_EXTENSIONS = {
    ".diff",
    ".json",
    ".md",
    ".patch",
    ".txt",
}

FORBIDDEN_KEY_FRAGMENTS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "cookie",
    "database_password",
    "db_password",
    "id_ed25519",
    "id_rsa",
    "password",
    "private_key",
    "session",
    "ssh_key",
    "token",
}

SECRET_TEXT_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|authorization|bearer|password|private[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{12,}"),
]

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
CHATGPT_ALIAS_MAX_CHARS = 80
MAX_TEXT_ARTIFACT_BYTES = 2_000_000
MAX_WORKSPACE_FILE_BYTES = 300_000
MAX_WORKSPACE_TOTAL_BYTES = 3_000_000
MAX_WORKSPACE_FILE_COUNT = 240


class AssistError(ValueError):
    """Raised when a no-API assist packet or artifact is invalid."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def storage_root(path: str | Path | None = None) -> Path:
    return Path(path).resolve() if path else DEFAULT_STORAGE_ROOT.resolve()


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssistError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise AssistError(f"{label} must be a string")
    if not allow_empty and not value.strip():
        raise AssistError(f"{label} must not be empty")
    return value


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise AssistError(f"{label} must be a boolean")
    return value


def optional_string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AssistError(f"{label} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(require_string(item, f"{label}[{index}]"))
    return result


def reject_sensitive_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            for fragment in FORBIDDEN_KEY_FRAGMENTS:
                if fragment in key_text:
                    raise AssistError(f"forbidden sensitive field name at {path}.{key}")
            reject_sensitive_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_sensitive_keys(child, f"{path}[{index}]")


def reject_secret_text(text: str, label: str) -> None:
    for pattern in SECRET_TEXT_PATTERNS:
        if pattern.search(text):
            raise AssistError(f"{label} appears to contain plaintext secret material")


def safe_id(value: str, label: str) -> str:
    value = require_string(value, label).strip()
    if not SAFE_ID_RE.fullmatch(value):
        raise AssistError(f"{label} must match {SAFE_ID_RE.pattern}")
    return value


def safe_chatgpt_alias(value: str, label: str) -> str:
    alias = require_string(value, label).strip()
    if len(alias) > CHATGPT_ALIAS_MAX_CHARS:
        raise AssistError(f"{label} must be at most {CHATGPT_ALIAS_MAX_CHARS} characters")
    if "://" in alias or "/" in alias or "\\" in alias:
        raise AssistError(f"{label} must be a plain user-visible alias, not a URL or path")
    if any(ord(char) < 32 or ord(char) == 127 for char in alias):
        raise AssistError(f"{label} must not contain control characters")
    lowered = alias.lower()
    for fragment in FORBIDDEN_KEY_FRAGMENTS | {"chatgpt.com", "localstorage", "oauth", "share"}:
        if fragment in lowered:
            raise AssistError(f"{label} appears to contain a private or sensitive reference")
    reject_secret_text(alias, label)
    return alias


def generate_run_id(task_id: str | None = None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if task_id:
        task = re.sub(r"[^A-Za-z0-9._-]+", "-", task_id).strip("-")[:32]
        if task:
            return f"{task}-{stamp}"
    return f"chatgpt-app-{stamp}"


def safe_filename(value: str) -> str:
    value = require_string(value, "filename").strip()
    if "/" in value or "\\" in value or ".." in value:
        raise AssistError("filename must be a plain file name, not a path")
    if not SAFE_FILENAME_RE.fullmatch(value):
        raise AssistError(f"filename must match {SAFE_FILENAME_RE.pattern}")
    suffix = Path(value).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise AssistError(f"filename extension is not allowed: {suffix}")
    return value


def run_dir(root: Path, run_id: str) -> Path:
    return root / safe_id(run_id, "run_id")


def relative_to_root(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise AssistError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AssistError(f"invalid JSON file: {path}: {exc}") from exc
    return require_mapping(payload, str(path))


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_assist_run(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "create_assist_run arguments")
    reject_sensitive_keys(args)

    if require_bool(args.get("redaction_confirmed"), "redaction_confirmed") is not True:
        raise AssistError("redaction_confirmed must be true before sending work to ChatGPT")

    goal = require_string(args.get("goal"), "goal")
    reject_secret_text(goal, "goal")
    task_id = args.get("task_id")
    if task_id is not None:
        task_id = safe_id(require_string(task_id, "task_id"), "task_id")

    run_id = args.get("run_id")
    run_id = safe_id(require_string(run_id, "run_id"), "run_id") if run_id else generate_run_id(task_id)

    root = storage_root(root)
    workspace = None
    if args.get("workspace_id") is not None:
        workspace = get_registered_workspace(require_string(args.get("workspace_id"), "workspace_id"), root)
    target = run_dir(root, run_id)
    if target.exists():
        raise AssistError(f"run already exists: {run_id}")
    target.mkdir(parents=True)
    (target / "incoming").mkdir()

    request = {
        "packet_type": "chatgpt_app_no_api_request",
        "channel": CHANNEL,
        "task_id": task_id,
        "run_id": run_id,
        "created_at": now_iso(),
        "goal": goal,
        "scope": optional_string_list(args.get("scope"), "scope"),
        "constraints": optional_string_list(args.get("constraints"), "constraints"),
        "expected_artifacts": optional_string_list(args.get("expected_artifacts"), "expected_artifacts"),
        "verification_commands": optional_string_list(args.get("verification_commands"), "verification_commands"),
        "api_model_calls_allowed": False,
        "local_supervisor_required": True,
        "workspace": workspace,
        "redaction": {
            "status": "confirmed",
            "confirmed_by": require_string(args.get("redaction_confirmed_by", "user"), "redaction_confirmed_by"),
        },
    }
    write_json_file(target / "request.json", request)
    write_json_file(
        target / "artifact-manifest.json",
        {
            "packet_type": "chatgpt_app_no_api_artifact_manifest",
            "channel": CHANNEL,
            "run_id": run_id,
            "artifacts": [],
        },
    )

    return {
        "ok": True,
        "run_id": run_id,
        "workspace_id": workspace["workspace_id"] if workspace else None,
        "request_path": relative_to_root(target / "request.json"),
        "incoming_dir": relative_to_root(target / "incoming"),
        "next_step": "Submit candidate artifacts with submit_candidate_artifact. Do not claim local verification.",
    }


def workspace_registry_path(root: Path | None = None) -> Path:
    return storage_root(root) / WORKSPACE_REGISTRY_FILE


def normalize_relative_path(value: str, label: str = "path") -> str:
    value = require_string(value, label).replace("\\", "/").strip()
    if not value or value in {".", "./"}:
        return "."
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise AssistError(f"{label} must be a safe relative path")
    return pure.as_posix()


def resolve_under_root(root_path: Path, relative_path: str) -> Path:
    relative_path = normalize_relative_path(relative_path)
    candidate = root_path if relative_path == "." else root_path / Path(*PurePosixPath(relative_path).parts)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_path.resolve())
    except ValueError as exc:
        raise AssistError(f"path escapes registered workspace: {relative_path}") from exc
    return resolved


def _string_list_from_entry(entry: dict[str, Any], keys: tuple[str, ...], default: list[str]) -> list[str]:
    for key in keys:
        if key in entry:
            return optional_string_list(entry.get(key), key)
    return default


def _normalize_workspace_entry(entry: dict[str, Any], index: int) -> dict[str, Any]:
    workspace_id = safe_id(require_string(entry.get("workspace_id"), f"workspaces[{index}].workspace_id"), "workspace_id")
    root_text = require_string(entry.get("root"), f"workspaces[{index}].root")
    root_path = Path(root_text).expanduser().resolve()
    if not root_path.is_dir():
        raise AssistError(f"registered workspace root is not a directory: {workspace_id}")

    include_paths = _string_list_from_entry(entry, ("include_paths", "default_include"), ["."])
    include_paths = [normalize_relative_path(item, "include_paths[]") for item in include_paths]
    exclude_patterns = set(DEFAULT_WORKSPACE_EXCLUDE_PATTERNS)
    exclude_patterns.update(_string_list_from_entry(entry, ("exclude_patterns", "default_exclude"), []))

    max_file_bytes = int(entry.get("max_file_bytes", MAX_WORKSPACE_FILE_BYTES))
    max_total_bytes = int(entry.get("max_total_bytes", MAX_WORKSPACE_TOTAL_BYTES))
    max_files = int(entry.get("max_files", MAX_WORKSPACE_FILE_COUNT))
    if max_file_bytes <= 0 or max_total_bytes <= 0 or max_files <= 0:
        raise AssistError(f"workspace limits must be positive: {workspace_id}")

    return {
        "workspace_id": workspace_id,
        "display_name": require_string(entry.get("display_name", workspace_id), f"workspaces[{index}].display_name"),
        "description": require_string(entry.get("description", ""), f"workspaces[{index}].description", allow_empty=True),
        "root": root_path.as_posix(),
        "include_paths": include_paths,
        "exclude_patterns": sorted(exclude_patterns),
        "max_file_bytes": max_file_bytes,
        "max_total_bytes": max_total_bytes,
        "max_files": max_files,
    }


def load_workspace_registry(root: Path | None = None) -> dict[str, Any]:
    path = workspace_registry_path(root)
    payload = read_json_file(path)
    workspaces = payload.get("workspaces")
    if not isinstance(workspaces, list):
        raise AssistError("workspace registry must contain a workspaces list")
    normalized = [_normalize_workspace_entry(require_mapping(item, f"workspaces[{index}]"), index) for index, item in enumerate(workspaces)]
    seen: set[str] = set()
    for workspace in normalized:
        workspace_id = workspace["workspace_id"]
        if workspace_id in seen:
            raise AssistError(f"duplicate workspace_id in registry: {workspace_id}")
        seen.add(workspace_id)
    return {
        "packet_type": "chatgpt_app_workspace_registry",
        "registry_path": relative_to_root(path),
        "workspaces": normalized,
    }


def get_registered_workspace(workspace_id: str, root: Path | None = None) -> dict[str, Any]:
    workspace_id = safe_id(workspace_id, "workspace_id")
    registry = load_workspace_registry(root)
    for workspace in registry["workspaces"]:
        if workspace["workspace_id"] == workspace_id:
            return workspace
    raise AssistError(f"workspace_id is not registered: {workspace_id}")


def list_registered_workspaces(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "list_registered_workspaces arguments")
    include_roots = bool(args.get("include_roots", True))
    registry = load_workspace_registry(root)
    workspaces = []
    for workspace in registry["workspaces"]:
        item = {
            "workspace_id": workspace["workspace_id"],
            "display_name": workspace["display_name"],
            "description": workspace["description"],
            "include_paths": workspace["include_paths"],
        }
        if include_roots:
            item["root"] = workspace["root"]
        workspaces.append(item)
    return {
        "ok": True,
        "registry_path": registry["registry_path"],
        "workspaces": workspaces,
        "next_step": "Create an assist run with the selected workspace_id before asking for source files.",
    }


def workspace_for_args(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    if args.get("run_id"):
        run_id = safe_id(require_string(args.get("run_id"), "run_id"), "run_id")
        request = read_json_file(run_dir(storage_root(root), run_id) / "request.json")
        workspace = request.get("workspace")
        if not isinstance(workspace, dict) or not workspace.get("workspace_id"):
            raise AssistError(f"run has no registered workspace: {run_id}")
        return get_registered_workspace(require_string(workspace.get("workspace_id"), "workspace.workspace_id"), root)
    if args.get("workspace_id"):
        return get_registered_workspace(require_string(args.get("workspace_id"), "workspace_id"), root)
    raise AssistError("workspace_id or run_id is required")


def _matches_workspace_exclude(relative_path: str, workspace: dict[str, Any], *, allow_structure_placeholder: bool = False) -> bool:
    lower_path = relative_path.lower()
    parts = {part.lower() for part in PurePosixPath(relative_path).parts}
    if parts & FORBIDDEN_WORKSPACE_PATH_PARTS:
        return True
    for fragment in FORBIDDEN_KEY_FRAGMENTS:
        if fragment in lower_path:
            return True
    for pattern in workspace["exclude_patterns"]:
        if PurePosixPath(relative_path).match(pattern) or PurePosixPath(lower_path).match(pattern.lower()):
            return True
    if allow_structure_placeholder and Path(relative_path).name in STRUCTURE_PLACEHOLDER_FILENAMES:
        return False
    suffix = Path(relative_path).suffix.lower()
    if suffix not in ALLOWED_WORKSPACE_EXTENSIONS:
        return True
    return False


def _iter_workspace_candidates(workspace: dict[str, Any], paths: list[str] | None = None) -> list[Path]:
    root_path = Path(workspace["root"]).resolve()
    include_paths = paths if paths is not None else workspace["include_paths"]
    candidates: list[Path] = []
    for relative in include_paths:
        target = resolve_under_root(root_path, relative)
        if target.is_file():
            candidates.append(target)
        elif target.is_dir():
            candidates.extend(path for path in target.rglob("*") if path.is_file())
    return sorted(set(candidates), key=lambda item: item.as_posix().lower())


def _safe_workspace_directory(workspace: dict[str, Any], path: Path) -> str | None:
    root_path = Path(workspace["root"]).resolve()
    resolved = path.resolve()
    try:
        relative_path = resolved.relative_to(root_path).as_posix()
    except ValueError:
        return None
    if relative_path == "." or path.is_symlink():
        return None
    lower_path = relative_path.lower()
    parts = {part.lower() for part in PurePosixPath(relative_path).parts}
    if parts & FORBIDDEN_WORKSPACE_PATH_PARTS:
        return None
    for fragment in FORBIDDEN_KEY_FRAGMENTS:
        if fragment in lower_path:
            return None
    for pattern in workspace["exclude_patterns"]:
        if PurePosixPath(relative_path).match(pattern) or PurePosixPath(lower_path).match(pattern.lower()):
            return None
    return relative_path


def list_workspace_directories(workspace: dict[str, Any], paths: list[str] | None = None) -> list[str]:
    root_path = Path(workspace["root"]).resolve()
    include_paths = paths if paths is not None else workspace["include_paths"]
    directories: set[str] = set()
    for relative in include_paths:
        target = resolve_under_root(root_path, relative)
        if target.is_file():
            current = _safe_workspace_directory(workspace, target.parent)
            if current is not None:
                directories.add(current)
            continue
        if target.is_dir():
            current = _safe_workspace_directory(workspace, target)
            if current is not None:
                directories.add(current)
            for child in target.rglob("*"):
                if child.is_dir():
                    current = _safe_workspace_directory(workspace, child)
                    if current is not None:
                        directories.add(current)
    return sorted(directories, key=str.lower)


def _safe_workspace_file(workspace: dict[str, Any], path: Path) -> dict[str, Any] | None:
    root_path = Path(workspace["root"]).resolve()
    resolved = path.resolve()
    try:
        relative_path = resolved.relative_to(root_path).as_posix()
    except ValueError:
        return None
    if path.is_symlink() or _matches_workspace_exclude(relative_path, workspace, allow_structure_placeholder=True):
        return None
    size = path.stat().st_size
    if size > int(workspace["max_file_bytes"]):
        return None
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return None
    reject_secret_text(content, f"workspace file {relative_path}")
    return {
        "path": relative_path,
        "size_bytes": len(content.encode("utf-8")),
        "sha256": sha256_text(content),
        "content": content,
    }


def list_workspace_files(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "list_workspace_files arguments")
    workspace = workspace_for_args(args, root)
    paths = args.get("paths")
    include_paths = None if paths is None else [normalize_relative_path(item, "paths[]") for item in optional_string_list(paths, "paths")]
    files = []
    total_bytes = 0
    skipped = 0
    for path in _iter_workspace_candidates(workspace, include_paths):
        try:
            item = _safe_workspace_file(workspace, path)
        except AssistError:
            skipped += 1
            continue
        if item is None:
            skipped += 1
            continue
        total_bytes += int(item["size_bytes"])
        if len(files) >= int(workspace["max_files"]) or total_bytes > int(workspace["max_total_bytes"]):
            skipped += 1
            break
        files.append({key: item[key] for key in ("path", "size_bytes", "sha256")})
    return {
        "ok": True,
        "workspace_id": workspace["workspace_id"],
        "root": workspace["root"],
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(int(item["size_bytes"]) for item in files),
        "skipped_count": skipped,
        "next_step": "Read only the files needed for the task with read_workspace_file.",
    }


def _run_git_context_command(workspace_root: Path, args: list[str]) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(workspace_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def collect_git_context(workspace_root: Path) -> dict[str, Any]:
    """Collect minimal git context for a shallow single-commit snapshot."""
    root = workspace_root.resolve()
    inside = _run_git_context_command(root, ["rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        return {
            "is_git_worktree": False,
            "branch": None,
            "head_commit": None,
            "head_subject": None,
            "worktree_root": root.as_posix(),
            "history_depth": 0,
            "history_policy": "no_git_repository",
            "branch_pack_policy": "none",
            "git_repository_included": False,
            "dirty": None,
        }
    branch = _run_git_context_command(root, ["branch", "--show-current"]) or "DETACHED"
    head_commit = _run_git_context_command(root, ["rev-parse", "HEAD"])
    head_subject = _run_git_context_command(root, ["log", "-1", "--pretty=%s"])
    status = _run_git_context_command(root, ["status", "--porcelain=v1"])
    return {
        "is_git_worktree": True,
        "branch": branch,
        "head_commit": head_commit,
        "head_subject": head_subject,
        "worktree_root": root.as_posix(),
        "history_depth": 1 if head_commit else 0,
        "history_policy": "shallow_single_commit_git_repo",
        "branch_pack_policy": "current_branch_only",
        "git_repository_included": bool(head_commit),
        "dirty": bool(status),
        "status_porcelain": status or "",
    }


def read_workspace_file(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "read_workspace_file arguments")
    workspace = workspace_for_args(args, root)
    relative_path = normalize_relative_path(require_string(args.get("path"), "path"))
    target = resolve_under_root(Path(workspace["root"]).resolve(), relative_path)
    if not target.is_file():
        raise AssistError(f"workspace file does not exist: {relative_path}")
    item = _safe_workspace_file(workspace, target)
    if item is None:
        raise AssistError(f"workspace file is not allowed or is too large: {relative_path}")
    return {
        "ok": True,
        "workspace_id": workspace["workspace_id"],
        "path": item["path"],
        "size_bytes": item["size_bytes"],
        "sha256": item["sha256"],
        "content": item["content"],
    }


def _write_workspace_snapshot_files(snapshot_root: Path, files: list[dict[str, Any]], directories: list[str], workspace_id: str, run_id: str) -> None:
    for entry in files:
        target = snapshot_root / Path(*PurePosixPath(str(entry["path"])).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(str(entry["content"]))
    for directory in directories:
        (snapshot_root / Path(*PurePosixPath(directory).parts)).mkdir(parents=True, exist_ok=True)

    metadata_root = snapshot_root / ".chatgpt-harness"
    metadata_root.mkdir(parents=True, exist_ok=True)
    directory_manifest = {
        "packet_type": "chatgpt_app_workspace_directory_structure",
        "run_id": run_id,
        "workspace_id": workspace_id,
        "mode": "relative_workspace_paths",
        "directories": directories,
    }
    (metadata_root / "directory-structure.json").write_text(
        json.dumps(directory_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ignore_harness_metadata(snapshot_root: Path) -> None:
    exclude_path = snapshot_root / ".git" / "info" / "exclude"
    if not exclude_path.exists():
        return
    content = exclude_path.read_text(encoding="utf-8", errors="replace")
    if "/.chatgpt-harness/" not in content:
        separator = "" if content.endswith(("\n", "\r")) or not content else "\n"
        exclude_path.write_text(f"{content}{separator}/.chatgpt-harness/\n", encoding="utf-8")


def _run_snapshot_git(snapshot_root: Path, args: list[str]) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(snapshot_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssistError(f"git {' '.join(args)} failed while building source bundle: {completed.stderr.strip()}")


def _sparse_checkout_patterns(files: list[dict[str, Any]], directories: list[str]) -> list[str]:
    patterns: set[str] = set()
    for entry in files:
        relative = normalize_relative_path(str(entry["path"]), "bundle file path")
        if relative != ".":
            patterns.add(f"/{relative}")
    for directory in directories:
        relative = normalize_relative_path(directory, "bundle directory")
        if relative != ".":
            patterns.add(f"/{relative}/")
    patterns.add("/.chatgpt-harness/")
    return sorted(patterns, key=str.lower)


def _apply_sparse_checkout(snapshot_root: Path, files: list[dict[str, Any]], directories: list[str]) -> None:
    _run_snapshot_git(snapshot_root, ["sparse-checkout", "init", "--no-cone"])
    patterns = _sparse_checkout_patterns(files, directories)
    sparse_file = snapshot_root / ".git" / "info" / "sparse-checkout"
    sparse_file.parent.mkdir(parents=True, exist_ok=True)
    sparse_file.write_text("\n".join(patterns) + "\n", encoding="utf-8", newline="\n")
    _run_snapshot_git(snapshot_root, ["read-tree", "-mu", "HEAD"])


def _write_git_snapshot_bundle(
    *,
    workspace_root: Path,
    snapshot_root: Path,
    files: list[dict[str, Any]],
    directories: list[str],
    workspace_id: str,
    run_id: str,
    git_context: dict[str, Any],
) -> None:
    head_commit = git_context.get("head_commit")
    snapshot_root.mkdir(parents=True, exist_ok=True)

    _write_workspace_snapshot_files(snapshot_root, files, directories, workspace_id, run_id)
    if git_context.get("is_git_worktree") is True and head_commit:
        git_context["history_depth"] = 0
        git_context["history_policy"] = "metadata_only_no_git_directory_uploaded"
        git_context["branch_pack_policy"] = "metadata_only_current_branch_name"
        git_context["git_repository_included"] = False
        git_context["snapshot_head_commit"] = head_commit
        git_context["snapshot_commit_policy"] = "metadata_only_preserve_original_head_reference"
        git_context["worktree_crop_policy"] = "manifested_files_plus_harness_metadata_no_git_directory"
        git_context["snapshot_note"] = "Uploaded source bundle preserves current dirty worktree file contents for manifested files and records Git metadata only; .git history is not uploaded."

    metadata_root = snapshot_root / ".chatgpt-harness"
    metadata_root.mkdir(parents=True, exist_ok=True)
    (metadata_root / "git-context.json").write_text(
        json.dumps(git_context, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _is_git_metadata_entry(path: Path, snapshot_root: Path) -> bool:
    try:
        relative = path.relative_to(snapshot_root).as_posix()
    except ValueError:
        return True
    return relative == ".git" or relative.startswith(".git/")


def create_workspace_bundle(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "create_workspace_bundle arguments")
    run_id = safe_id(require_string(args.get("run_id"), "run_id"), "run_id")
    workspace = workspace_for_args(args, root)
    listed = list_workspace_files(args, root)
    run_path = run_dir(storage_root(root), run_id)
    if not (run_path / "request.json").exists():
        raise AssistError(f"unknown run_id: {run_id}")

    bundle_path = run_path / "source-files.zip"
    manifest_path = run_path / "source-files-manifest.json"
    files: list[dict[str, Any]] = []
    git_context = collect_git_context(Path(workspace["root"]).resolve())
    include_paths = args.get("paths")
    normalized_paths = None if include_paths is None else [normalize_relative_path(item, "paths[]") for item in optional_string_list(include_paths, "paths")]
    directories = list_workspace_directories(workspace, normalized_paths)
    for entry in listed["files"]:
        content_result = read_workspace_file(
            {"workspace_id": workspace["workspace_id"], "path": entry["path"]},
            root,
        )
        files.append(
            {
                "path": entry["path"],
                "size_bytes": entry["size_bytes"],
                "sha256": entry["sha256"],
                "content": str(content_result["content"]),
            }
        )
    with tempfile.TemporaryDirectory(prefix=f"{run_id}-git-snapshot-") as tmp_dir:
        snapshot_root = Path(tmp_dir) / "snapshot"
        _write_git_snapshot_bundle(
            workspace_root=Path(workspace["root"]).resolve(),
            snapshot_root=snapshot_root,
            files=files,
            directories=directories,
            workspace_id=workspace["workspace_id"],
            run_id=run_id,
            git_context=git_context,
        )
        archive_files = sorted(
            (path for path in snapshot_root.rglob("*") if path.is_file() and not _is_git_metadata_entry(path, snapshot_root)),
            key=lambda item: item.as_posix().lower(),
        )
        archive_dirs = sorted(
            (path for path in snapshot_root.rglob("*") if path.is_dir() and not _is_git_metadata_entry(path, snapshot_root)),
            key=lambda item: item.as_posix().lower(),
        )
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for directory in archive_dirs:
                if directory == snapshot_root:
                    continue
                relative = directory.relative_to(snapshot_root).as_posix()
                if not any(child.is_file() for child in directory.iterdir()):
                    archive.writestr(f"{relative.rstrip('/')}/", "")
            for path in archive_files:
                archive.write(path, path.relative_to(snapshot_root).as_posix())
    manifest_files = [{key: entry[key] for key in ("path", "size_bytes", "sha256")} for entry in files]
    manifest = {
        "packet_type": "chatgpt_app_workspace_bundle_manifest",
        "channel": CHANNEL,
        "run_id": run_id,
        "workspace_id": workspace["workspace_id"],
        "created_at": now_iso(),
        "bundle_path": relative_to_root(bundle_path),
        "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        "path_preservation": {
            "mode": "relative_workspace_paths",
            "empty_directories": "preserve_with_zip_directory_entries",
            "directory_structure": ".chatgpt-harness/directory-structure.json",
            "metadata_prefix": ".chatgpt-harness/",
        },
        "git_context": git_context,
        "directories": directories,
        "files": manifest_files,
        "file_count": len(manifest_files),
        "total_bytes": sum(int(item["size_bytes"]) for item in manifest_files),
        "skipped_count": listed["skipped_count"],
    }
    write_json_file(manifest_path, manifest)
    return {
        "ok": True,
        "run_id": run_id,
        "workspace_id": workspace["workspace_id"],
        "bundle_path": relative_to_root(bundle_path),
        "manifest_path": relative_to_root(manifest_path),
        "bundle_sha256": manifest["bundle_sha256"],
        "path_preservation": manifest["path_preservation"],
        "git_context": git_context,
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "next_step": "Upload the bundle manually to ChatGPT Project only after the local operator reviews the manifest.",
    }


def load_manifest(target: Path) -> dict[str, Any]:
    manifest_path = target / "artifact-manifest.json"
    if manifest_path.exists():
        manifest = read_json_file(manifest_path)
    else:
        manifest = {
            "packet_type": "chatgpt_app_no_api_artifact_manifest",
            "channel": CHANNEL,
            "run_id": target.name,
            "artifacts": [],
        }
    if manifest.get("channel") != CHANNEL:
        raise AssistError("artifact manifest channel is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise AssistError("artifact manifest artifacts must be a list")
    return manifest


def submit_candidate_artifact(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "submit_candidate_artifact arguments")
    reject_sensitive_keys(args)

    run_id = safe_id(require_string(args.get("run_id"), "run_id"), "run_id")
    artifact_type = require_string(args.get("artifact_type"), "artifact_type")
    if artifact_type not in ALLOWED_ARTIFACT_TYPES:
        raise AssistError(f"artifact_type is not allowed: {artifact_type}")

    filename = safe_filename(require_string(args.get("filename"), "filename"))
    content = require_string(args.get("content"), "content", allow_empty=True)
    encoded_size = len(content.encode("utf-8"))
    if encoded_size > MAX_TEXT_ARTIFACT_BYTES:
        raise AssistError(f"content exceeds {MAX_TEXT_ARTIFACT_BYTES} bytes")
    reject_secret_text(content, "content")

    root = storage_root(root)
    target = run_dir(root, run_id)
    if not (target / "request.json").exists():
        raise AssistError(f"unknown run_id: {run_id}")
    incoming = target / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    artifact_path = incoming / filename
    if artifact_path.exists() and not bool(args.get("overwrite", False)):
        raise AssistError(f"artifact already exists: {filename}")
    artifact_path.write_text(content, encoding="utf-8")

    digest = sha256_text(content)
    manifest = load_manifest(target)
    artifact = {
        "name": filename,
        "path": relative_to_root(artifact_path),
        "type": artifact_type,
        "sha256": digest,
        "producer": PRODUCER,
        "created_at": now_iso(),
        "size_bytes": encoded_size,
    }
    artifacts = [item for item in manifest["artifacts"] if item.get("name") != filename]
    artifacts.append(artifact)
    manifest["artifacts"] = artifacts
    write_json_file(target / "artifact-manifest.json", manifest)

    return {
        "ok": True,
        "run_id": run_id,
        "artifact": artifact,
        "next_step": "Ask local Codex supervisor to inspect or verify this run.",
    }


def list_candidate_artifacts(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "list_candidate_artifacts arguments")
    run_id = safe_id(require_string(args.get("run_id"), "run_id"), "run_id")
    target = run_dir(storage_root(root), run_id)
    manifest = load_manifest(target)
    return {
        "ok": True,
        "run_id": run_id,
        "artifacts": manifest["artifacts"],
    }


def get_supervisor_receipt(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "get_supervisor_receipt arguments")
    run_id = safe_id(require_string(args.get("run_id"), "run_id"), "run_id")
    receipt_path = run_dir(storage_root(root), run_id) / "local-supervisor-receipt.json"
    if not receipt_path.exists():
        return {
            "ok": True,
            "run_id": run_id,
            "status": "not_ready",
            "message": "Local Codex supervisor has not written a receipt yet.",
        }
    receipt = read_json_file(receipt_path)
    return {
        "ok": True,
        "run_id": run_id,
        "status": receipt.get("status") or receipt.get("local_gate_status"),
        "receipt": receipt,
    }


def request_revision(args: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    args = require_mapping(args, "request_revision arguments")
    reject_sensitive_keys(args)
    run_id = safe_id(require_string(args.get("run_id"), "run_id"), "run_id")
    message = require_string(args.get("message"), "message")
    reject_secret_text(message, "message")
    target = run_dir(storage_root(root), run_id)
    if not target.exists():
        raise AssistError(f"unknown run_id: {run_id}")
    entry = {
        "created_at": now_iso(),
        "run_id": run_id,
        "message": message,
        "blocking": bool(args.get("blocking", True)),
    }
    path = target / "revision-requests.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "ok": True,
        "run_id": run_id,
        "revision_request_path": relative_to_root(path),
    }


def validate_artifact_manifest(run_id: str, root: Path | None = None) -> dict[str, Any]:
    target = run_dir(storage_root(root), run_id)
    request = read_json_file(target / "request.json")
    if request.get("channel") != CHANNEL:
        raise AssistError("request channel is invalid")
    if request.get("api_model_calls_allowed") is not False:
        raise AssistError("request must set api_model_calls_allowed to false")
    if request.get("local_supervisor_required") is not True:
        raise AssistError("request must require a local supervisor")
    reject_sensitive_keys(request)

    manifest = load_manifest(target)
    checked: list[dict[str, Any]] = []
    for index, artifact in enumerate(manifest["artifacts"]):
        artifact = require_mapping(artifact, f"artifacts[{index}]")
        name = safe_filename(require_string(artifact.get("name"), f"artifacts[{index}].name"))
        artifact_type = require_string(artifact.get("type"), f"artifacts[{index}].type")
        if artifact_type not in ALLOWED_ARTIFACT_TYPES:
            raise AssistError(f"artifacts[{index}].type is not allowed: {artifact_type}")
        expected_sha = require_string(artifact.get("sha256"), f"artifacts[{index}].sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise AssistError(f"artifacts[{index}].sha256 must be 64 lowercase hex characters")
        path = target / "incoming" / name
        content = path.read_text(encoding="utf-8")
        reject_secret_text(content, f"artifact {name}")
        actual_sha = sha256_text(content)
        if actual_sha != expected_sha:
            raise AssistError(f"artifact hash mismatch for {name}")
        checked.append(
            {
                "name": name,
                "path": relative_to_root(path),
                "type": artifact_type,
                "sha256": actual_sha,
                "producer": artifact.get("producer", PRODUCER),
            }
        )
    return {
        "ok": True,
        "run_id": run_id,
        "request": request,
        "artifacts": checked,
    }
