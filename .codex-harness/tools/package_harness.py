#!/usr/bin/env python3
"""Package, install, and verify the project-local Codex harness.

The installer is intentionally project-local: it writes the harness under a
target workspace's `.codex-harness/` directory and appends a small managed entry
to the target `AGENTS.md`. It does not write global Codex configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


PACKAGE_ID = "codex_project_harness"
PACKAGE_VERSION = 1
INSTALL_ROOT = ".codex-harness"
PACKAGE_NAME = "codex-project-harness.zip"
MANIFEST_NAME = "harness-package.json"
INSTALL_RECEIPT = "receipts/install-receipt.json"
VERIFY_RECEIPT = "receipts/verify-receipt.json"
LOCAL_SECRET_ENV_RECEIPT = "receipts/local-secret-env-receipt.json"
AGENTS_MARKER_BEGIN = "# codex-harness:start"
AGENTS_MARKER_END = "# codex-harness:end"
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PACKAGE_ASSETS = (
    "configs/harness-provider-registry.json",
    "configs/harness-evaluation-registry.json",
    "docs/chatgpt-app-no-api-supervised-workflow.md",
    "docs/chatgpt-web-manual-assist-workflow.md",
    "docs/chatgpt-web-project-conversation-demo.md",
    "docs/chatgpt-web-workload-and-entry-design.md",
    "docs/codex-led-harness-architecture.md",
    "docs/codex-led-harness-open-source-ecosystem-research-2026-06-02.md",
    "docs/codex-sdk-language-decision.md",
    "docs/codex_tooling_inventory.md",
    "docs/executor-materialization-profile.md",
    "docs/executor-run-contract.md",
    "docs/harness-evaluation-standards-2026-06-02.md",
    "docs/project-local-harness-installation.md",
    "docs/project-capability-profile.md",
    "docs/protocol-boundaries.md",
    "prompt_groups/codex_harness/README.md",
    "prompt_groups/codex_harness/chatgpt_web_manual_assist.md",
    "prompt_groups/codex_harness/codex_executor.md",
    "prompt_groups/codex_harness/task_payload_template.md",
    "schemas/executor_run_contract.schema.json",
    "tools/chatgpt_app_no_api_common.py",
    "tools/chatgpt_app_no_api_connector.py",
    "tools/chatgpt_app_proxy.py",
    "tools/chatgpt_app_supervisor.py",
    "tools/chatgpt_web_artifact_importer.py",
    "tools/chatgpt_web_execution_dispatcher.py",
    "tools/chatgpt_web_harness.py",
    "tools/chatgpt_web_project_conversation_demo.py",
    "tools/chatgpt_web_simprint_bridge.py",
    "tools/package_harness.py",
    "tools/probe_codex_sdk_capabilities.py",
    "tools/validate_chatgpt_web_manual_assist.py",
    "tools/validate_executor_contract.py",
    "tools/validate_harness_alignment.py",
    "tools/validate_harness_evaluation_registry.py",
    "tools/validate_harness_provider_registry.py",
)


JSON = dict[str, Any]


class PackageError(ValueError):
    """Raised when packaging, installation, or verification fails."""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> JSON:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PackageError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_asset_path(value: str) -> str:
    pure = PurePosixPath(value.replace("\\", "/"))
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PackageError(f"unsafe package asset path: {value}")
    return pure.as_posix()


def _load_source_assets(source_root: Path) -> list[JSON]:
    source_root = source_root.resolve()
    assets: list[JSON] = []
    for asset in PACKAGE_ASSETS:
        rel = _normalize_asset_path(asset)
        path = source_root / rel
        if not path.is_file():
            raise PackageError(f"required harness asset is missing: {rel}")
        size = path.stat().st_size
        assets.append(
            {
                "path": rel,
                "sha256": sha256_file(path),
                "size_bytes": size,
            }
        )
    return assets


def _generated_assets() -> list[JSON]:
    agents_payload = _installed_harness_agents_md().encode("utf-8")
    return [
        {
            "path": "AGENTS.md",
            "sha256": sha256_bytes(agents_payload),
            "size_bytes": len(agents_payload),
            "generated": True,
        }
    ]


def _package_metadata(source_root: Path, assets: list[JSON]) -> JSON:
    return {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "created_at": now_iso(),
        "install_root": INSTALL_ROOT,
        "source_root_name": source_root.name,
        "asset_count": len(assets),
        "assets": assets,
        "policy": {
            "project_local_only": True,
            "writes_global_codex_config": False,
            "delivery_authority": "local_codex_supervisor",
        },
    }


def _installed_harness_agents_md() -> str:
    return """# Project-Local Codex Harness Guide

This guide applies to the installed `.codex-harness/` directory in the current
project.

## Purpose

- This project has a project-local Codex-led multi-agent coding harness.
- The harness prepares scoped code context, analyzes requirements, designs
  serial/parallel work, dispatches candidate agents, verifies results, records
  receipts, and preserves reusable lessons.
- This installation is project-local. Do not treat it as a global Codex
  configuration.

## Read First

- `docs/codex-led-harness-architecture.md`
- `docs/codex-sdk-language-decision.md`
- `docs/project-local-harness-installation.md`
- `docs/codex_tooling_inventory.md`
- `docs/project-capability-profile.md`
- `docs/protocol-boundaries.md`
- `prompt_groups/codex_harness/README.md`

## Boundary Rules

- Local Codex supervisor is the delivery authority for this project.
- ChatGPT Web and ChatGPT App no-API flows are candidate-artifact assist
  channels; they are not local verification or delivery authorities.
- CodexSDK means the official Python `openai-codex` SDK adapter only; Codex CLI
  remains the fallback local execution backend.
- CursorSDK/Cursor CLI support requires real Cursor authentication. Without it,
  only capability probes or blocked receipts are valid.
- Provider-specific handles, session IDs, credentials, browser tokens, and
  product internals must stay out of run contracts and tracked assets.

## Verification

Run from the target project root:

```powershell
$python = "C:\\Users\\Administration\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe"
& $python .codex-harness\\tools\\package_harness.py verify --target .
```
"""


def create_package(source_root: str | Path, output_dir: str | Path) -> Path:
    """Create a portable harness zip package and return its path."""

    source_root = Path(source_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = _generated_assets() + _load_source_assets(source_root)
    metadata = _package_metadata(source_root, assets)
    package_path = output_dir / PACKAGE_NAME
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        archive.writestr("AGENTS.md", _installed_harness_agents_md())
        for asset in assets:
            rel = str(asset["path"])
            if asset.get("generated"):
                continue
            archive.write(source_root / rel, rel)
    return package_path


def _safe_archive_members(archive: zipfile.ZipFile) -> list[str]:
    names = archive.namelist()
    if MANIFEST_NAME not in names:
        raise PackageError(f"package is missing {MANIFEST_NAME}")
    for name in names:
        rel = _normalize_asset_path(name)
        if rel != name.replace("\\", "/"):
            raise PackageError(f"archive member is not normalized: {name}")
    return names


def _read_package_metadata(package_path: Path) -> JSON:
    try:
        with zipfile.ZipFile(package_path) as archive:
            _safe_archive_members(archive)
            metadata = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise PackageError(f"cannot read harness package {package_path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise PackageError(f"{MANIFEST_NAME} must contain a JSON object")
    if metadata.get("package_id") != PACKAGE_ID:
        raise PackageError("package_id mismatch")
    if metadata.get("install_root") != INSTALL_ROOT:
        raise PackageError("install_root mismatch")
    assets = metadata.get("assets")
    if not isinstance(assets, list) or not assets:
        raise PackageError("package assets must not be empty")
    return metadata


def _verify_package_hashes(package_path: Path, metadata: JSON) -> None:
    expected = {str(asset["path"]): asset for asset in metadata["assets"]}
    with zipfile.ZipFile(package_path) as archive:
        names = set(_safe_archive_members(archive))
        missing = sorted(set(expected) - names)
        if missing:
            raise PackageError(f"package is missing assets: {missing}")
        for rel, asset in expected.items():
            payload = archive.read(rel)
            digest = sha256_bytes(payload)
            if digest != asset.get("sha256"):
                raise PackageError(f"package asset sha256 mismatch: {rel}")


def _is_managed_install(install_root: Path) -> bool:
    receipt_path = install_root / INSTALL_RECEIPT
    if not receipt_path.is_file():
        return False
    try:
        receipt = read_json(receipt_path)
    except PackageError:
        return False
    return receipt.get("package_id") == PACKAGE_ID and receipt.get("install_root") == INSTALL_ROOT


def _extract_package(package_path: Path, install_root: Path) -> None:
    with zipfile.ZipFile(package_path) as archive:
        for name in _safe_archive_members(archive):
            rel = _normalize_asset_path(name)
            target = install_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))


def _remove_previous_managed_assets(install_root: Path) -> None:
    """Remove only manifest-managed files, preserving runtime state and receipts."""

    manifest_path = install_root / MANIFEST_NAME
    if not manifest_path.exists():
        return
    try:
        metadata = read_json(manifest_path)
    except PackageError:
        return
    assets = metadata.get("assets")
    if not isinstance(assets, list):
        return
    managed_paths = {MANIFEST_NAME}
    for asset in assets:
        if isinstance(asset, dict) and isinstance(asset.get("path"), str):
            managed_paths.add(_normalize_asset_path(str(asset["path"])))
    for rel in sorted(managed_paths, reverse=True):
        target = install_root / rel
        if target.is_file() or target.is_symlink():
            target.unlink()


def _managed_agents_entry() -> str:
    return "\n".join(
        [
            AGENTS_MARKER_BEGIN,
            "This project has a project-local Codex harness installed under `.codex-harness/`.",
            "Read `.codex-harness/AGENTS.md` and `.codex-harness/docs/codex_tooling_inventory.md` before harness work.",
            "Use `.codex-harness/tools/package_harness.py verify --target .` to verify the installed harness.",
            "Do not treat assist-channel artifacts as delivered until the local supervisor receipt passes.",
            AGENTS_MARKER_END,
            "",
        ]
    )


def _write_project_agents_entry(target_root: Path, *, force: bool = False) -> None:
    agents_path = target_root / "AGENTS.md"
    entry = _managed_agents_entry()
    if not agents_path.exists():
        agents_path.write_text(entry, encoding="utf-8")
        return
    text = agents_path.read_text(encoding="utf-8-sig")
    if AGENTS_MARKER_BEGIN in text:
        before, rest = text.split(AGENTS_MARKER_BEGIN, 1)
        if AGENTS_MARKER_END not in rest:
            if not force:
                raise PackageError("AGENTS.md contains an incomplete codex harness managed block")
            text = before.rstrip() + "\n\n" + entry
        else:
            _, after = rest.split(AGENTS_MARKER_END, 1)
            text = before.rstrip() + "\n\n" + entry + after.lstrip()
        agents_path.write_text(text, encoding="utf-8")
        return
    agents_path.write_text(text.rstrip() + "\n\n" + entry, encoding="utf-8")


def install_package(package_path: str | Path, target_root: str | Path, *, force: bool = False) -> JSON:
    """Install a package into target_root/.codex-harness and return a receipt."""

    package_path = Path(package_path).resolve()
    target_root = Path(target_root).resolve()
    if not target_root.exists():
        target_root.mkdir(parents=True)
    if not target_root.is_dir():
        raise PackageError(f"target is not a directory: {target_root}")

    metadata = _read_package_metadata(package_path)
    _verify_package_hashes(package_path, metadata)
    install_root = target_root / INSTALL_ROOT

    if install_root.exists():
        if not _is_managed_install(install_root):
            if not force:
                raise PackageError(f"existing unmanaged harness install at {install_root}; use --force to replace it")
            shutil.rmtree(install_root)
        else:
            _remove_previous_managed_assets(install_root)
    install_root.mkdir(parents=True, exist_ok=True)
    _extract_package(package_path, install_root)

    receipt = {
        "package_id": PACKAGE_ID,
        "package_version": metadata.get("package_version"),
        "status": "installed",
        "installed_at": now_iso(),
        "install_root": INSTALL_ROOT,
        "target_root": str(target_root),
        "package_path": str(package_path),
        "asset_count": len(metadata["assets"]),
        "package_sha256": sha256_file(package_path),
    }
    write_json(install_root / INSTALL_RECEIPT, receipt)
    _write_project_agents_entry(target_root, force=force)
    return receipt


def _env_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise PackageError(f"invalid env line {line_number}: missing '='")
        key = line.split("=", 1)[0].strip()
        if not ENV_KEY_RE.fullmatch(key):
            raise PackageError(f"invalid env key on line {line_number}: {key!r}")
        keys.append(key)
    if not keys:
        raise PackageError("secret env file must contain at least one key")
    return sorted(set(keys))


def _relative_under(root: Path, target: Path, label: str) -> str:
    try:
        return target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise PackageError(f"{label} must stay inside target_root") from exc


def _is_git_ignored(target_root: Path, relative_path: str) -> bool:
    git_dir = target_root / ".git"
    if not git_dir.exists():
        return False
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative_path],
        cwd=str(target_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return completed.returncode == 0


def copy_local_secret_env(
    source: str | Path,
    target: str | Path,
    *,
    target_root: str | Path,
    overwrite: bool = True,
) -> JSON:
    """Copy a local env companion file and write a redacted receipt."""

    source_path = Path(source).resolve()
    target_root_path = Path(target_root).resolve()
    target_path = Path(target).resolve()
    if not source_path.is_file():
        raise PackageError(f"source secret env file is missing: {source_path}")
    if not target_root_path.is_dir():
        raise PackageError(f"target_root is not a directory: {target_root_path}")
    relative_target = _relative_under(target_root_path, target_path, "target")
    if relative_target.startswith(f"{INSTALL_ROOT}/"):
        raise PackageError("local secret env target must stay outside .codex-harness so reinstall cannot delete it")
    keys = _env_keys(source_path)
    target_git_ignored = _is_git_ignored(target_root_path, relative_target)
    if not target_git_ignored:
        raise PackageError(f"local secret env target must be git-ignored before copying: {relative_target}")
    if target_path.exists() and not overwrite:
        raise PackageError(f"target secret env already exists: {target_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    receipt = {
        "package_id": PACKAGE_ID,
        "status": "copied",
        "copied_at": now_iso(),
        "target_root": str(target_root_path),
        "source_path": str(source_path),
        "target_path": str(target_path),
        "target_relative_path": relative_target,
        "target_git_ignored": target_git_ignored,
        "key_count": len(keys),
        "keys": keys,
        "values": {key: "<redacted>" for key in keys},
        "values_policy": "not_recorded_no_hash_no_length",
    }
    write_json(target_root_path / INSTALL_ROOT / LOCAL_SECRET_ENV_RECEIPT, receipt)
    return receipt


def _load_installed_manifest(install_root: Path) -> JSON:
    manifest_path = install_root / MANIFEST_NAME
    metadata = read_json(manifest_path)
    if metadata.get("package_id") != PACKAGE_ID:
        raise PackageError("installed harness package_id mismatch")
    if metadata.get("install_root") != INSTALL_ROOT:
        raise PackageError("installed harness install_root mismatch")
    if not isinstance(metadata.get("assets"), list) or not metadata["assets"]:
        raise PackageError("installed harness manifest has no assets")
    return metadata


def _run_validator(command: list[str], *, cwd: Path) -> JSON:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "name": Path(command[1]).name if len(command) > 1 else command[0],
        "command": command,
        "exit_code": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def verify_installation(target_root: str | Path, *, run_validators: bool = True, write_receipt_file: bool = True) -> JSON:
    """Verify an installed project-local harness and return a receipt."""

    target_root = Path(target_root).resolve()
    install_root = target_root / INSTALL_ROOT
    if not install_root.is_dir():
        raise PackageError(f"installed harness not found at {install_root}")
    metadata = _load_installed_manifest(install_root)
    install_receipt = read_json(install_root / INSTALL_RECEIPT)
    if install_receipt.get("package_id") != PACKAGE_ID:
        raise PackageError("install receipt package_id mismatch")

    checks: list[JSON] = []
    for asset in metadata["assets"]:
        rel = _normalize_asset_path(str(asset.get("path", "")))
        path = install_root / rel
        if not path.is_file():
            raise PackageError(f"installed asset missing: {rel}")
        digest = sha256_file(path)
        if digest != asset.get("sha256"):
            raise PackageError(f"sha256 mismatch for installed asset: {rel}")
    checks.append({"name": "asset_hashes", "status": "passed", "asset_count": len(metadata["assets"])})

    agents_text = (target_root / "AGENTS.md").read_text(encoding="utf-8-sig")
    if AGENTS_MARKER_BEGIN not in agents_text or AGENTS_MARKER_END not in agents_text:
        raise PackageError("target AGENTS.md is missing the managed codex harness entry")
    checks.append({"name": "project_agents_entry", "status": "passed"})

    if run_validators:
        validator_commands = [
            [
                sys.executable,
                "tools/validate_harness_provider_registry.py",
                "configs/harness-provider-registry.json",
            ],
            [
                sys.executable,
                "tools/validate_harness_evaluation_registry.py",
                "configs/harness-evaluation-registry.json",
            ],
            [
                sys.executable,
                "tools/validate_harness_alignment.py",
                ".",
            ],
        ]
        for command in validator_commands:
            check = _run_validator(command, cwd=install_root)
            checks.append(check)
            if check["status"] != "passed":
                raise PackageError(f"installed validator failed: {check['name']}: {check['stderr_tail']}")

    local_secret_receipt = install_root / LOCAL_SECRET_ENV_RECEIPT
    if local_secret_receipt.exists():
        secret_receipt = read_json(local_secret_receipt)
        target_relative = _normalize_asset_path(str(secret_receipt.get("target_relative_path", "")))
        target_path = target_root / target_relative
        if not target_path.is_file():
            raise PackageError("local secret env receipt target is missing")
        keys = _env_keys(target_path)
        expected_keys = secret_receipt.get("keys")
        if keys != expected_keys:
            raise PackageError("local secret env key set mismatch")
        if not _is_git_ignored(target_root, target_relative):
            raise PackageError("local secret env target is no longer git-ignored")
        checks.append(
            {
                "name": "local_secret_env_companion",
                "status": "passed",
                "target_relative_path": target_relative,
                "keys": keys,
                "values_policy": "not_recorded_no_hash_no_length",
            }
        )

    receipt = {
        "package_id": PACKAGE_ID,
        "package_version": metadata.get("package_version"),
        "status": "passed",
        "verified_at": now_iso(),
        "install_root": INSTALL_ROOT,
        "target_root": str(target_root),
        "checks": checks,
    }
    if write_receipt_file:
        write_json(install_root / VERIFY_RECEIPT, receipt)
    return receipt


def _print_json(payload: JSON) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    pack_parser = subparsers.add_parser("pack", help="Create a portable harness package")
    pack_parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    pack_parser.add_argument("--output-dir", type=Path, default=Path("dist"))

    install_parser = subparsers.add_parser("install", help="Install a harness package into a target project")
    install_parser.add_argument("--package", type=Path, required=True)
    install_parser.add_argument("--target", type=Path, required=True)
    install_parser.add_argument("--force", action="store_true")

    verify_parser = subparsers.add_parser("verify", help="Verify a project-local harness installation")
    verify_parser.add_argument("--target", type=Path, required=True)
    verify_parser.add_argument("--skip-validators", action="store_true")
    verify_parser.add_argument("--no-write-receipt", action="store_true")

    secret_parser = subparsers.add_parser("copy-local-secret-env", help="Copy a local secret env companion and write a redacted receipt")
    secret_parser.add_argument("--source", type=Path, required=True)
    secret_parser.add_argument("--target", type=Path, required=True)
    secret_parser.add_argument("--target-root", type=Path, required=True)
    secret_parser.add_argument("--no-overwrite", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            package_path = create_package(args.source, args.output_dir)
            _print_json({"ok": True, "package_path": str(package_path), "package_sha256": sha256_file(package_path)})
        elif args.command == "install":
            receipt = install_package(args.package, args.target, force=args.force)
            _print_json({"ok": True, "receipt": receipt})
        elif args.command == "verify":
            receipt = verify_installation(
                args.target,
                run_validators=not args.skip_validators,
                write_receipt_file=not args.no_write_receipt,
            )
            _print_json({"ok": True, "receipt": receipt})
        elif args.command == "copy-local-secret-env":
            receipt = copy_local_secret_env(
                args.source,
                args.target,
                target_root=args.target_root,
                overwrite=not args.no_overwrite,
            )
            _print_json({"ok": True, "receipt": receipt})
        else:
            raise PackageError(f"unknown command: {args.command}")
    except PackageError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
