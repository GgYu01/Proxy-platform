from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import TextIO

from proxy_platform.manifest import ManifestError, PlatformManifest, load_manifest
from proxy_platform.toolchain import diagnose_toolchain_profile
from proxy_platform.workspace import (
    build_init_plan,
    build_sync_plan,
    collect_repo_statuses,
    diagnose_workspace,
    initialize_workspace,
    sync_workspace,
)


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv or sys.argv[1:], stdout=sys.stdout, stderr=sys.stderr)


def run_cli(argv: list[str], *, stdout: TextIO, stderr: TextIO | None = None) -> int:
    stderr = stderr or io.StringIO()
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    if args.command == "help":
        parser.print_help(stdout)
        return 0

    try:
        manifest = _load_manifest_from_args(args)
    except ManifestError as exc:
        stderr.write(f"{exc}\n")
        return 2

    if args.command == "manifest" and args.manifest_command == "validate":
        stdout.write(f"manifest: ok ({manifest.name} {manifest.version})\n")
        stdout.write(f"supported modes: {', '.join(manifest.supported_modes)}\n")
        return 0

    mode = getattr(args, "mode", manifest.default_mode)
    workspace_root = Path(getattr(args, "workspace_root", manifest.source_path.parent)).resolve()

    if args.command == "repos" and args.repos_command == "list":
        for status in collect_repo_statuses(manifest, workspace_root, mode):
            stdout.write(
                f"{status.repo_id}\trole={status.role}\tvisibility={status.visibility}\t"
                f"required={str(status.required).lower()}\texists={str(status.exists).lower()}\t"
                f"path={status.selected_path}\n"
            )
        return 0

    if args.command == "doctor" and getattr(args, "doctor_command", None) == "toolchain":
        profile = manifest.toolchains.get(args.profile)
        if profile is None:
            stderr.write(f"unknown toolchain profile: {args.profile}\n")
            return 2
        diagnosis = diagnose_toolchain_profile(profile, os_release_path=args.os_release_path)
        stdout.write(
            f"doctor-toolchain: profile={profile.profile_id} ok={str(diagnosis.ok).lower()}\n"
        )
        stdout.write(
            f"os: {diagnosis.os_release.pretty_name} "
            f"(id={diagnosis.os_release.system_id} version={diagnosis.os_release.version_id})\n"
        )
        python_selected = diagnosis.python.selected_command or "none"
        python_path = diagnosis.python.selected_path or "none"
        python_version = diagnosis.python.version or "none"
        stdout.write(
            f"python: ok={str(diagnosis.python.ok).lower()} min={diagnosis.python.min_version} "
            f"selected={python_selected} path={python_path} version={python_version}"
        )
        if diagnosis.python.env_hint:
            stdout.write(f" env_hint={diagnosis.python.env_hint}")
        stdout.write("\n")
        for command in diagnosis.commands:
            if command.ok:
                stdout.write(f"- {command.command_id}: ok=true version={command.version}\n")
            else:
                stdout.write(f"- {command.command_id}: ok=false detail={command.detail}\n")
        return 0 if diagnosis.ok else 2

    if args.command == "doctor":
        diagnosis = diagnose_workspace(manifest, workspace_root, mode)
        stdout.write(f"doctor: mode={mode} ok={str(diagnosis.ok).lower()}\n")
        for status in diagnosis.repo_statuses:
            override = (
                f" local_override={status.local_override_path}"
                if status.local_override_exists and status.local_override_path
                else ""
            )
            stdout.write(
                f"- {status.repo_id}: exists={str(status.exists).lower()} required={str(status.required).lower()} "
                f"path={status.selected_path}{override}\n"
            )
        if diagnosis.missing_required:
            stdout.write("missing required repos:\n")
            for status in diagnosis.missing_required:
                stdout.write(f"  - {status.repo_id}\n")
            return 1
        return 0

    if args.command == "init":
        lines = build_init_plan(manifest, workspace_root, mode) if args.dry_run else initialize_workspace(
            manifest, workspace_root, mode
        )
        for line in lines:
            stdout.write(f"{line}\n")
        return 2 if _has_unresolved_repo_action(lines) else 0

    if args.command == "sync":
        lines = build_sync_plan(manifest, workspace_root, mode) if args.dry_run else sync_workspace(
            manifest, workspace_root, mode
        )
        for line in lines:
            stdout.write(f"{line}\n")
        return 2 if _has_unresolved_repo_action(lines) else 0

    stderr.write("unsupported command\n")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proxy-platform", description="Thin orchestration shell for the proxy platform.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    help_parser = subparsers.add_parser("help", help="Show command help")
    help_parser.set_defaults(command="help")

    manifest_parser = subparsers.add_parser("manifest", help="Manifest operations")
    manifest_subparsers = manifest_parser.add_subparsers(dest="manifest_command", required=True)
    manifest_validate_parser = manifest_subparsers.add_parser("validate", help="Validate manifest")
    manifest_validate_parser.add_argument("--manifest", default="platform.manifest.yaml")

    repos_parser = subparsers.add_parser("repos", help="Workspace repo operations")
    repos_subparsers = repos_parser.add_subparsers(dest="repos_command", required=True)
    repos_list_parser = repos_subparsers.add_parser("list", help="List repo statuses")
    repos_list_parser.add_argument("--manifest", default="platform.manifest.yaml")
    repos_list_parser.add_argument("--workspace-root", default=".")
    repos_list_parser.add_argument("--mode", default=None)

    doctor_parser = subparsers.add_parser("doctor", help="Diagnose workspace state")
    doctor_parser.add_argument("--manifest", default="platform.manifest.yaml")
    doctor_parser.add_argument("--workspace-root", default=".")
    doctor_parser.add_argument("--mode", default=None)
    doctor_subparsers = doctor_parser.add_subparsers(dest="doctor_command", required=False)
    doctor_toolchain_parser = doctor_subparsers.add_parser("toolchain", help="Diagnose host toolchain")
    doctor_toolchain_parser.add_argument("--manifest", default="platform.manifest.yaml")
    doctor_toolchain_parser.add_argument("--profile", required=True)
    doctor_toolchain_parser.add_argument("--os-release-path", default="/etc/os-release")

    init_parser = subparsers.add_parser("init", help="Initialize workspace")
    init_parser.add_argument("--manifest", default="platform.manifest.yaml")
    init_parser.add_argument("--workspace-root", default=".")
    init_parser.add_argument("--mode", default=None)
    init_parser.add_argument("--dry-run", action="store_true")

    sync_parser = subparsers.add_parser("sync", help="Sync workspace")
    sync_parser.add_argument("--manifest", default="platform.manifest.yaml")
    sync_parser.add_argument("--workspace-root", default=".")
    sync_parser.add_argument("--mode", default=None)
    sync_parser.add_argument("--dry-run", action="store_true")

    return parser


def _load_manifest_from_args(args: argparse.Namespace) -> PlatformManifest:
    manifest_value = getattr(args, "manifest", "platform.manifest.yaml")
    return load_manifest(Path(manifest_value))


def _has_unresolved_repo_action(lines: list[str]) -> bool:
    unresolved_markers = (
        "remote clone not implemented yet",
        "failed to clone",
        "failed to fetch",
    )
    return any(any(marker in line for marker in unresolved_markers) for line in lines)
