from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import TextIO

from proxy_platform.manifest import ManifestError, PlatformManifest, load_manifest
from proxy_platform.inventory import load_host_registry
from proxy_platform.projections import build_host_views, build_subscription_projection
from proxy_platform.providers import describe_local_providers
from proxy_platform.state import build_host_views as build_state_host_views
from proxy_platform.state import load_host_observations
from proxy_platform.state import load_host_registry as load_state_host_registry
from proxy_platform.state import project_subscription
from proxy_platform.state import StateFileError
from proxy_platform.toolchain import diagnose_toolchain_profile
from proxy_platform.web_app import run_web_console
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

    if args.command == "hosts" and args.registry:
        try:
            registry = load_state_host_registry(args.registry)
            observations = load_host_observations(args.observations) if args.observations else None
        except StateFileError as exc:
            stderr.write(f"{exc}\n")
            return 2
        for view in build_state_host_views(registry, observations):
            stdout.write(
                f"{view.host_id}\tdesired={view.desired_state}\tobserved={view.observed_status}\t"
                f"subscription={str(view.subscription_included).lower()}\tprovider={view.provider}\t"
                f"endpoint={view.endpoint}\tsource={view.observation_source}\n"
            )
        return 0

    if args.command == "subscriptions" and args.registry:
        try:
            registry = load_state_host_registry(args.registry)
            observations = load_host_observations(args.observations) if args.observations else None
        except StateFileError as exc:
            stderr.write(f"{exc}\n")
            return 2
        projection = project_subscription(registry, observations)
        stdout.write(f"subscription-preview: members={len(projection.members)}\n")
        for member in projection.members:
            stdout.write(
                f"- {member.host_id}: endpoint={member.endpoint} provider={member.provider} "
                f"observed={member.observed_status} reason={member.reason}\n"
            )
        if projection.excluded_host_ids:
            stdout.write(f"excluded hosts: {', '.join(projection.excluded_host_ids)}\n")
        if projection.unknown_observation_host_ids:
            stdout.write(
                f"unknown observation hosts: {', '.join(projection.unknown_observation_host_ids)}\n"
            )
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

    mode = getattr(args, "mode", None) or manifest.default_mode
    workspace_root = Path(getattr(args, "workspace_root", manifest.source_path.parent)).resolve()

    if args.command == "hosts" and args.hosts_command == "list":
        try:
            host_registry_source = _require_host_registry_source(manifest, mode)
        except ManifestError as exc:
            stderr.write(f"{exc}\n")
            return 2
        registry = load_host_registry(host_registry_source, workspace_root)
        views = build_host_views(registry)
        publishable = sum(1 for view in views if view.should_publish)
        stdout.write(f"hosts: total={len(views)} publishable={publishable}\n")
        for view in views:
            stdout.write(
                f"- {view.name}: observed={view.observed_health} publish={str(view.should_publish).lower()} "
                f"provider={view.provider} host={view.host} ssh_port={view.ssh_port} "
                f"change_policy={view.change_policy}\n"
            )
        return 0

    if args.command == "subscriptions" and args.subscriptions_command == "list":
        try:
            host_registry_source = _require_host_registry_source(manifest, mode)
        except ManifestError as exc:
            stderr.write(f"{exc}\n")
            return 2
        registry = load_host_registry(host_registry_source, workspace_root)
        projection = build_subscription_projection(registry)
        stdout.write(f"multi_node_url={projection.multi_node_url}\n")
        stdout.write(f"multi_node_hiddify={projection.multi_node_hiddify_import}\n")
        stdout.write(f"remote_profile_url={projection.remote_profile_url}\n")
        for node in projection.per_node:
            stdout.write(
                f"- {node.name}: alias={node.alias} v2ray_url={node.v2ray_url} "
                f"hiddify_url={node.hiddify_import_url}\n"
            )
        return 0

    if args.command == "providers" and args.providers_command == "list":
        providers = describe_local_providers(manifest)
        stdout.write(f"providers: total={len(providers)}\n")
        for provider in providers:
            owner_fragment = f" owner_repo={provider.owner_repo_id}" if provider.owner_repo_id else ""
            stdout.write(
                f"- {provider.provider_id}: kind={provider.kind} startup_timeout={provider.startup_timeout_seconds} "
                f"request_timeout={provider.request_timeout_seconds} startup_attempts={provider.startup_max_attempts} "
                f"request_attempts={provider.request_max_attempts}{owner_fragment}\n"
            )
        return 0

    if args.command == "web":
        run_web_console(
            manifest_path=getattr(args, "manifest", "platform.manifest.yaml"),
            workspace_root=workspace_root,
            mode=mode,
            host=args.host,
            port=args.port,
        )
        return 0

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

    hosts_parser = subparsers.add_parser("hosts", help="Platform host registry views")
    hosts_parser.add_argument("--registry", default=None)
    hosts_parser.add_argument("--observations", default=None)
    hosts_subparsers = hosts_parser.add_subparsers(dest="hosts_command", required=False)
    hosts_list_parser = hosts_subparsers.add_parser("list", help="List hosts from configured registry sources")
    hosts_list_parser.add_argument("--manifest", default="platform.manifest.yaml")
    hosts_list_parser.add_argument("--workspace-root", default=".")
    hosts_list_parser.add_argument("--mode", default=None)

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

    subscriptions_parser = subparsers.add_parser("subscriptions", help="Subscription projections")
    subscriptions_parser.add_argument("--registry", default=None)
    subscriptions_parser.add_argument("--observations", default=None)
    subscriptions_subparsers = subscriptions_parser.add_subparsers(dest="subscriptions_command", required=False)
    subscriptions_list_parser = subscriptions_subparsers.add_parser(
        "list",
        help="List derived subscription URLs from configured registry sources",
    )
    subscriptions_list_parser.add_argument("--manifest", default="platform.manifest.yaml")
    subscriptions_list_parser.add_argument("--workspace-root", default=".")
    subscriptions_list_parser.add_argument("--mode", default=None)
    subscriptions_preview_parser = subscriptions_subparsers.add_parser(
        "preview",
        help="Preview subscription members from direct registry and observation files",
    )
    subscriptions_preview_parser.add_argument("--registry", required=True)
    subscriptions_preview_parser.add_argument("--observations", default=None)

    providers_parser = subparsers.add_parser("providers", help="Local provider lifecycle policies")
    providers_subparsers = providers_parser.add_subparsers(dest="providers_command", required=True)
    providers_list_parser = providers_subparsers.add_parser("list", help="List provider retry/timeout budgets")
    providers_list_parser.add_argument("--manifest", default="platform.manifest.yaml")

    web_parser = subparsers.add_parser("web", help="Run the minimal platform web console")
    web_parser.add_argument("--manifest", default="platform.manifest.yaml")
    web_parser.add_argument("--workspace-root", default=".")
    web_parser.add_argument("--mode", default=None)
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)

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


def _require_host_registry_source(manifest: PlatformManifest, mode: str):
    if manifest.host_registry is None:
        raise ManifestError("host registry source is not configured")
    if not manifest.host_registry.applies_to_mode(mode):
        raise ManifestError(f"host registry source is not configured for mode {mode}")
    return manifest.host_registry
