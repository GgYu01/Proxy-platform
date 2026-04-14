from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from datetime import timezone
import hashlib
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from proxy_platform.inventory import add_host_record
from proxy_platform.inventory import load_host_registry
from proxy_platform.inventory import remove_host_record
from proxy_platform.manifest import JobsConfig
from proxy_platform.manifest import ManifestError
from proxy_platform.manifest import PlatformManifest


class JobConfigError(ManifestError):
    """Raised when job orchestration is not configured for the current mode."""


class JobApplyUnsupportedError(ValueError):
    """Raised when a job is dry-run only in the current phase."""


class JobPlanIntegrityError(ValueError):
    """Raised when a saved plan no longer matches the reviewed plan contract."""


@dataclass(frozen=True)
class JobPlan:
    job_id: str
    job_kind: str
    mode: str
    requested_by: str
    summary: str
    created_at: str
    apply_supported: bool
    requires_confirmation: bool
    executor: str
    payload: dict[str, Any]
    preview_steps: tuple[str, ...]
    source_refs: tuple[str, ...]
    warnings: tuple[str, ...]
    status: str
    plan_path: Path
    plan_digest: str


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    event: str
    job_id: str
    job_kind: str
    mode: str
    requested_by: str
    created_at: str
    status: str
    summary: str
    plan_path: str
    plan_digest: str


@dataclass(frozen=True)
class JobApplyResult:
    job_id: str
    status: str
    audit_id: str
    effect: str
    plan_path: Path


def plan_job(
    *,
    manifest: PlatformManifest,
    workspace_root: str | Path,
    mode: str,
    job_kind: str,
    requested_by: str,
    payload: dict[str, Any],
    output_path: str | Path | None = None,
) -> JobPlan:
    jobs = _require_jobs_config(manifest, mode)
    policy = jobs.policy_for(job_kind)
    root = Path(workspace_root).resolve()
    host_registry = _require_host_registry(manifest, mode)
    registry = load_host_registry(host_registry, root)
    now = _now()
    job_id = _build_job_id(now, job_kind)
    summary, preview_steps, source_refs, warnings = _plan_details(
        job_kind=job_kind,
        payload=payload,
        registry=registry,
        host_inventory_path=_resolve_relative(root, host_registry.inventory_path),
    )
    plan_path = _resolve_managed_plan_path(jobs, root, output_path, job_id)
    seed = JobPlan(
        job_id=job_id,
        job_kind=job_kind,
        mode=mode,
        requested_by=requested_by,
        summary=summary,
        created_at=_isoformat(now),
        apply_supported=policy.allow_apply,
        requires_confirmation=jobs.require_confirmation,
        executor=policy.executor,
        payload=dict(payload),
        preview_steps=tuple(preview_steps),
        source_refs=tuple(source_refs),
        warnings=tuple(warnings),
        status="planned",
        plan_path=plan_path,
        plan_digest="",
    )
    plan = replace(seed, plan_digest=_job_plan_digest(seed))
    _write_job_plan(plan)
    _append_audit_record(
        jobs=jobs,
        workspace_root=root,
        record=AuditRecord(
            audit_id=f"{job_id}-planned",
            event="planned",
            job_id=job_id,
            job_kind=job_kind,
            mode=mode,
            requested_by=requested_by,
            created_at=plan.created_at,
            status="planned",
            summary=summary,
            plan_path=str(plan.plan_path),
            plan_digest=plan.plan_digest,
        ),
    )
    return plan


def apply_job_plan(
    *,
    manifest: PlatformManifest,
    workspace_root: str | Path,
    mode: str,
    plan: JobPlan,
    requested_by: str,
    confirm: bool,
) -> JobApplyResult:
    jobs = _require_jobs_config(manifest, mode)
    root = Path(workspace_root).resolve()
    _validate_managed_plan_path(jobs, root, plan.plan_path)

    if plan.status != "planned":
        raise JobPlanIntegrityError("only planned jobs can be applied")
    if plan.plan_digest != _job_plan_digest(plan):
        raise JobPlanIntegrityError("plan digest mismatch, plan file may have been modified")

    planned_record = _find_planned_audit_record(manifest, root, mode, plan.job_id)
    if planned_record is None:
        raise JobPlanIntegrityError("planned audit record is missing for current job")
    if planned_record.plan_digest != plan.plan_digest or planned_record.plan_path != str(plan.plan_path):
        raise JobPlanIntegrityError("planned audit record does not match current plan")
    if _find_applied_audit_record(manifest, root, mode, plan.job_id) is not None:
        raise JobPlanIntegrityError("job has already been applied and cannot be replayed")

    if jobs.require_confirmation and not confirm:
        raise ValueError("job apply requires explicit confirmation")
    _validate_current_job_policy(jobs, plan)

    host_registry = _require_host_registry(manifest, mode)
    effect = _apply_supported_job(
        job_kind=plan.job_kind,
        payload=plan.payload,
        host_registry_source=host_registry,
        workspace_root=root,
    )
    updated = replace(plan, status="applied")
    _write_job_plan(updated)
    audit_id = f"{plan.job_id}-applied"
    _append_audit_record(
        jobs=jobs,
        workspace_root=root,
        record=AuditRecord(
            audit_id=audit_id,
            event="applied",
            job_id=plan.job_id,
            job_kind=plan.job_kind,
            mode=mode,
            requested_by=requested_by,
            created_at=_isoformat(_now()),
            status="applied",
            summary=effect,
            plan_path=str(plan.plan_path),
            plan_digest=plan.plan_digest,
        ),
    )
    return JobApplyResult(
        job_id=plan.job_id,
        status="applied",
        audit_id=audit_id,
        effect=effect,
        plan_path=plan.plan_path,
    )


def load_job_plan(path: str | Path) -> JobPlan:
    plan_path = Path(path)
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise JobPlanIntegrityError(f"unknown plan file: {plan_path}") from exc
    except (OSError, JSONDecodeError) as exc:
        raise JobPlanIntegrityError(f"failed to load plan file {plan_path}: {exc}") from exc
    return JobPlan(
        job_id=str(payload["job_id"]),
        job_kind=str(payload["job_kind"]),
        mode=str(payload["mode"]),
        requested_by=str(payload["requested_by"]),
        summary=str(payload["summary"]),
        created_at=str(payload["created_at"]),
        apply_supported=bool(payload["apply_supported"]),
        requires_confirmation=bool(payload["requires_confirmation"]),
        executor=str(payload["executor"]),
        payload=dict(payload["payload"]),
        preview_steps=tuple(str(item) for item in payload["preview_steps"]),
        source_refs=tuple(str(item) for item in payload["source_refs"]),
        warnings=tuple(str(item) for item in payload.get("warnings", [])),
        status=str(payload["status"]),
        plan_path=Path(payload["plan_path"]).resolve(),
        plan_digest=str(payload["plan_digest"]),
    )


def list_audit_records(manifest: PlatformManifest, workspace_root: str | Path, mode: str) -> list[AuditRecord]:
    jobs = _require_jobs_config(manifest, mode)
    audit_file = _audit_file_path(jobs, Path(workspace_root).resolve())
    if not audit_file.exists():
        return []
    records: list[AuditRecord] = []
    for raw_line in audit_file.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        records.append(
            AuditRecord(
                audit_id=str(payload["audit_id"]),
                event=str(payload["event"]),
                job_id=str(payload["job_id"]),
                job_kind=str(payload["job_kind"]),
                mode=str(payload["mode"]),
                requested_by=str(payload["requested_by"]),
                created_at=str(payload["created_at"]),
                status=str(payload["status"]),
                summary=str(payload["summary"]),
                plan_path=str(payload["plan_path"]),
                plan_digest=str(payload.get("plan_digest", "")),
            )
        )
    return list(reversed(records))


def resolve_job_plan_path(
    manifest: PlatformManifest,
    workspace_root: str | Path,
    mode: str,
    plan_path: str | Path,
) -> Path:
    jobs = _require_jobs_config(manifest, mode)
    resolved_root = Path(workspace_root).resolve()
    resolved_plan_path = Path(plan_path).resolve()
    _validate_managed_plan_path(jobs, resolved_root, resolved_plan_path)
    return resolved_plan_path


def load_payload_file(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping payload")
    return payload


def _require_jobs_config(manifest: PlatformManifest, mode: str) -> JobsConfig:
    if manifest.jobs is None:
        raise JobConfigError("jobs config is not configured")
    if not manifest.jobs.applies_to_mode(mode):
        raise JobConfigError(f"jobs config is not configured for mode {mode}")
    return manifest.jobs


def _require_host_registry(manifest: PlatformManifest, mode: str):
    if manifest.host_registry is None:
        raise JobConfigError("host registry source is not configured")
    if not manifest.host_registry.applies_to_mode(mode):
        raise JobConfigError(f"host registry source is not configured for mode {mode}")
    return manifest.host_registry


def _find_planned_audit_record(
    manifest: PlatformManifest,
    workspace_root: Path,
    mode: str,
    job_id: str,
) -> AuditRecord | None:
    for record in list_audit_records(manifest, workspace_root, mode):
        if record.job_id == job_id and record.event == "planned":
            return record
    return None


def _find_applied_audit_record(
    manifest: PlatformManifest,
    workspace_root: Path,
    mode: str,
    job_id: str,
) -> AuditRecord | None:
    for record in list_audit_records(manifest, workspace_root, mode):
        if record.job_id == job_id and record.event == "applied":
            return record
    return None


def _plan_details(
    *,
    job_kind: str,
    payload: dict[str, Any],
    registry,
    host_inventory_path: Path,
) -> tuple[str, list[str], list[str], list[str]]:
    node_names = {node.name for node in registry.nodes}
    if job_kind == "add_host":
        _validate_add_host_payload(payload)
        name = str(payload["name"])
        if name in node_names:
            raise ValueError(f"host already exists: {name}")
        return (
            f"add host {name} to operator registry",
            [
                f"validate host payload for {name}",
                f"write {name} into inventory file {host_inventory_path}",
                "leave remote deployment untouched in current phase",
            ],
            [str(host_inventory_path)],
            [],
        )
    if job_kind == "remove_host":
        name = str(payload["name"])
        if name not in node_names:
            raise KeyError(name)
        return (
            f"remove host {name} from operator registry",
            [
                f"validate existing host {name} in inventory",
                f"remove {name} from inventory file {host_inventory_path}",
                "leave remote runtime cleanup untouched in current phase",
            ],
            [str(host_inventory_path)],
            [],
        )
    if job_kind == "deploy_host":
        name = str(payload["name"])
        if name not in node_names:
            raise KeyError(name)
        return (
            f"plan remote deployment for host {name}",
            [
                f"validate host {name} exists in operator registry",
                f"would delegate deployment through remote_proxy lifecycle entrypoint for {name}",
                "executor is not configured, so this job remains dry-run only in current phase",
            ],
            [str(host_inventory_path), "repos/remote_proxy/scripts/service.sh"],
            ["remote deploy apply is intentionally blocked until executor wiring is added"],
        )
    if job_kind == "decommission_host":
        name = str(payload["name"])
        if name not in node_names:
            raise KeyError(name)
        return (
            f"plan remote decommission for host {name}",
            [
                f"validate host {name} exists in operator registry",
                f"would delegate decommission flow through remote_proxy lifecycle entrypoint for {name}",
                "executor is not configured, so this job remains dry-run only in current phase",
            ],
            [str(host_inventory_path), "repos/remote_proxy/scripts/service.sh"],
            ["remote decommission apply is intentionally blocked until executor wiring is added"],
        )
    raise ValueError(f"unsupported job kind: {job_kind}")


def _apply_supported_job(*, job_kind: str, payload: dict[str, Any], host_registry_source, workspace_root: Path) -> str:
    if job_kind == "add_host":
        record = add_host_record(host_registry_source, workspace_root, payload)
        return f"inventory updated with host {record.name}"
    if job_kind == "remove_host":
        removed = remove_host_record(host_registry_source, workspace_root, str(payload["name"]))
        return f"inventory removed host {removed}"
    raise JobApplyUnsupportedError(f"job kind {job_kind} is dry-run only in current phase")


def _validate_add_host_payload(payload: dict[str, Any]) -> None:
    required_fields = (
        "name",
        "host",
        "ssh_port",
        "base_port",
        "subscription_alias",
        "enabled",
        "infra_core_candidate",
        "change_policy",
        "provider",
    )
    optional_fields = ("include_in_subscription",)
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise ValueError(f"missing host payload field: {missing[0]}")
    allowed = set(required_fields + optional_fields)
    unexpected = [field for field in payload if field not in allowed]
    if unexpected:
        raise ValueError(f"unsupported host payload field: {unexpected[0]}")


def _validate_current_job_policy(jobs: JobsConfig, plan: JobPlan) -> None:
    current_policy = jobs.policy_for(plan.job_kind)
    if not current_policy.allow_apply:
        raise JobApplyUnsupportedError(f"job kind {plan.job_kind} is dry-run only in current phase")
    if not plan.apply_supported:
        raise JobPlanIntegrityError("plan apply policy no longer matches current job contract")
    if current_policy.executor != plan.executor:
        raise JobPlanIntegrityError("job executor changed after planning; create a new reviewed plan")


def _write_job_plan(plan: JobPlan) -> None:
    plan.plan_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(plan)
    payload["plan_path"] = str(plan.plan_path)
    plan.plan_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _append_audit_record(*, jobs: JobsConfig, workspace_root: Path, record: AuditRecord) -> None:
    audit_file = _audit_file_path(jobs, workspace_root)
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    with audit_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record)) + "\n")


def _resolve_managed_plan_path(
    jobs: JobsConfig,
    workspace_root: Path,
    candidate: str | Path | None,
    job_id: str,
) -> Path:
    plan_directory = _plan_directory(jobs, workspace_root)
    if candidate is None:
        return plan_directory / f"{job_id}.json"
    resolved_candidate = Path(candidate).resolve()
    _validate_managed_plan_path(jobs, workspace_root, resolved_candidate)
    return resolved_candidate


def _validate_managed_plan_path(jobs: JobsConfig, workspace_root: Path, plan_path: Path) -> None:
    plan_directory = _plan_directory(jobs, workspace_root)
    try:
        plan_path.relative_to(plan_directory)
    except ValueError as exc:
        raise JobPlanIntegrityError(f"plan path must stay inside {plan_directory}") from exc


def _plan_directory(jobs: JobsConfig, workspace_root: Path) -> Path:
    audit_dir = _resolve_relative(workspace_root, jobs.audit_path)
    return (audit_dir.parent / "plans").resolve()


def _audit_file_path(jobs: JobsConfig, workspace_root: Path) -> Path:
    return _resolve_relative(workspace_root, jobs.audit_path) / "events.jsonl"


def _job_plan_digest(plan: JobPlan) -> str:
    payload = {
        "job_id": plan.job_id,
        "job_kind": plan.job_kind,
        "mode": plan.mode,
        "requested_by": plan.requested_by,
        "summary": plan.summary,
        "created_at": plan.created_at,
        "apply_supported": plan.apply_supported,
        "requires_confirmation": plan.requires_confirmation,
        "executor": plan.executor,
        "payload": plan.payload,
        "preview_steps": list(plan.preview_steps),
        "source_refs": list(plan.source_refs),
        "warnings": list(plan.warnings),
        "plan_path": str(plan.plan_path),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_job_id(value: datetime, job_kind: str) -> str:
    return f"{value.strftime('%Y%m%dT%H%M%S%f')}-{job_kind}-{uuid4().hex[:8]}"


def _resolve_relative(workspace_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else workspace_root / path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
