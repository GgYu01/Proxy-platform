from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from proxy_platform.inventory import HostRecord
from proxy_platform.manifest import AuthorityAdapterSpec
from proxy_platform.manifest import JobsConfig
from proxy_platform.manifest import PlatformManifest


class AuthorityAdapterError(ValueError):
    """Raised when no stable downstream authority surface can be resolved."""


@dataclass(frozen=True)
class AuthorityResolution:
    adapter_id: str
    display_name: str
    owner_repo_id: str
    topology: str
    runtime_service: str
    handoff_method: str
    entrypoint: Path
    service_name: str | None
    action: str
    required_paths: tuple[Path, ...]
    downstream_required_paths: tuple[Path, ...]
    required_env_files: tuple[Path, ...]
    required_env_keys: tuple[str, ...]
    rollback_owner: str
    rollback_hint: str
    notes: tuple[str, ...]
    recommended_command: tuple[str, ...] | None


@dataclass(frozen=True)
class AuthorityHandoff:
    handoff_id: str
    job_id: str
    job_kind: str
    mode: str
    requested_by: str
    created_at: str
    plan_path: str
    plan_digest: str
    host: dict[str, object]
    adapter: dict[str, object]
    required_paths: tuple[str, ...]
    downstream_required_paths: tuple[str, ...]
    required_env_files: tuple[str, ...]
    required_env_keys: tuple[str, ...]
    recommended_command: tuple[str, ...] | None
    rollback_owner: str
    rollback_hint: str
    notes: tuple[str, ...]
    review_steps: tuple[str, ...]
    handoff_path: Path


def resolve_authority_adapter(
    manifest: PlatformManifest,
    *,
    mode: str,
    job_kind: str,
    host_record: HostRecord,
) -> AuthorityResolution:
    if host_record.deployment_topology in {"", "unknown"} or host_record.runtime_service in {"", "unknown"}:
        raise AuthorityAdapterError(
            f"host {host_record.name} is missing deployment classification; "
            "set deployment_topology and runtime_service before remote planning"
        )
    candidates = [
        adapter
        for adapter in manifest.authority_adapters.values()
        if adapter.applies_to_mode(mode)
        and job_kind in adapter.job_kinds
        and adapter.topology == host_record.deployment_topology
        and adapter.runtime_service == host_record.runtime_service
    ]
    if not candidates:
        raise AuthorityAdapterError(
            "no authority adapter is configured for "
            f"job {job_kind} topology {host_record.deployment_topology} "
            f"service {host_record.runtime_service}"
        )
    if len(candidates) > 1:
        adapter_ids = ", ".join(sorted(adapter.adapter_id for adapter in candidates))
        raise AuthorityAdapterError(
            f"multiple authority adapters match job {job_kind} for host {host_record.name}: {adapter_ids}"
        )
    adapter = candidates[0]
    action = adapter.actions[job_kind]
    recommended_command = _recommended_command(adapter, action)
    return AuthorityResolution(
        adapter_id=adapter.adapter_id,
        display_name=adapter.display_name,
        owner_repo_id=adapter.owner_repo_id,
        topology=adapter.topology,
        runtime_service=adapter.runtime_service,
        handoff_method=adapter.handoff_method,
        entrypoint=adapter.entrypoint,
        service_name=adapter.service_name,
        action=action,
        required_paths=adapter.required_paths,
        downstream_required_paths=adapter.downstream_required_paths,
        required_env_files=adapter.required_env_files,
        required_env_keys=adapter.required_env_keys,
        rollback_owner=adapter.rollback_owner,
        rollback_hint=adapter.rollback_hint,
        notes=adapter.notes,
        recommended_command=recommended_command,
    )


def validate_authority_prerequisites(*, workspace_root: Path, resolution: AuthorityResolution) -> None:
    missing: list[str] = []
    entrypoint_path = _resolve_relative(workspace_root, resolution.entrypoint)
    if not entrypoint_path.exists():
        missing.append(f"entrypoint {entrypoint_path}")
    for required_path in resolution.required_paths:
        resolved_path = _resolve_relative(workspace_root, required_path)
        if not resolved_path.exists():
            missing.append(f"required path {resolved_path}")

    resolved_env_files = [_resolve_relative(workspace_root, env_file) for env_file in resolution.required_env_files]
    for env_file in resolved_env_files:
        if not env_file.exists():
            missing.append(f"required env file {env_file}")

    present_env_keys: set[str] = set()
    for env_file in resolved_env_files:
        if env_file.exists():
            present_env_keys.update(_read_env_keys(env_file))
    for required_key in resolution.required_env_keys:
        if required_key not in present_env_keys:
            missing.append(f"required env key {required_key}")

    if missing:
        raise AuthorityAdapterError("authority prerequisites missing: " + "; ".join(missing))


def build_authority_handoff(
    *,
    jobs: JobsConfig,
    workspace_root: Path,
    requested_by: str,
    job_id: str,
    job_kind: str,
    mode: str,
    created_at: str,
    plan_path: Path,
    plan_digest: str,
    host_record: HostRecord,
    resolution: AuthorityResolution,
) -> AuthorityHandoff:
    if jobs.handoff_path is None:
        raise AuthorityAdapterError("jobs.handoff_path is not configured")
    handoff_dir = _resolve_relative(workspace_root, jobs.handoff_path)
    handoff_path = handoff_dir / f"{job_id}.yaml"
    review_steps = _review_steps(resolution)
    handoff = AuthorityHandoff(
        handoff_id=f"{job_id}-handoff",
        job_id=job_id,
        job_kind=job_kind,
        mode=mode,
        requested_by=requested_by,
        created_at=created_at,
        plan_path=str(plan_path),
        plan_digest=plan_digest,
        host=asdict(host_record),
        adapter={
            "adapter_id": resolution.adapter_id,
            "display_name": resolution.display_name,
            "owner_repo_id": resolution.owner_repo_id,
            "topology": resolution.topology,
            "runtime_service": resolution.runtime_service,
            "handoff_method": resolution.handoff_method,
            "entrypoint": str(resolution.entrypoint),
            "service_name": resolution.service_name,
            "action": resolution.action,
        },
        required_paths=tuple(str(path) for path in resolution.required_paths),
        downstream_required_paths=tuple(str(path) for path in resolution.downstream_required_paths),
        required_env_files=tuple(str(path) for path in resolution.required_env_files),
        required_env_keys=resolution.required_env_keys,
        recommended_command=resolution.recommended_command,
        rollback_owner=resolution.rollback_owner,
        rollback_hint=resolution.rollback_hint,
        notes=resolution.notes,
        review_steps=review_steps,
        handoff_path=handoff_path,
    )
    _write_handoff(handoff)
    return handoff


def _recommended_command(adapter: AuthorityAdapterSpec, action: str) -> tuple[str, ...] | None:
    if adapter.handoff_method != "service_script":
        return None
    repo_prefix = Path("repos") / adapter.owner_repo_id
    entrypoint = adapter.entrypoint
    if entrypoint.is_absolute():
        relative_entrypoint = entrypoint
    elif entrypoint.parts[: len(repo_prefix.parts)] == repo_prefix.parts:
        relative_entrypoint = Path(*entrypoint.parts[len(repo_prefix.parts) :])
    else:
        relative_entrypoint = entrypoint
    command = [f"./{relative_entrypoint.as_posix()}"]
    if adapter.service_name:
        command.append(adapter.service_name)
    command.append(action)
    return tuple(command)


def _review_steps(resolution: AuthorityResolution) -> tuple[str, ...]:
    steps = [
        f"review downstream owner repo {resolution.owner_repo_id}",
        f"confirm topology {resolution.topology} and runtime service {resolution.runtime_service}",
    ]
    if resolution.handoff_method == "service_script" and resolution.recommended_command is not None:
        steps.append(f"run {' '.join(resolution.recommended_command)} from the downstream repo root")
    else:
        steps.append(f"open {resolution.entrypoint} and execute the topology-specific procedure")
    if resolution.downstream_required_paths:
        joined_paths = ", ".join(str(path) for path in resolution.downstream_required_paths)
        steps.append(f"verify downstream execution paths exist: {joined_paths}")
    steps.append(f"rollback remains owned by {resolution.rollback_owner}")
    return tuple(steps)


def _read_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _value = line.split("=", 1)
        key = key.strip()
        if key:
            keys.add(key)
    return keys


def _resolve_relative(workspace_root: Path, value: Path) -> Path:
    return value if value.is_absolute() else workspace_root / value


def _write_handoff(handoff: AuthorityHandoff) -> None:
    handoff.handoff_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(handoff)
    payload["handoff_path"] = str(handoff.handoff_path)
    handoff.handoff_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
