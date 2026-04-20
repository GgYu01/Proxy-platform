from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


TRUTH_SYNC_RELATIVE_PATHS: tuple[str, ...] = (
    "repos/proxy_ops_private/inventory/nodes.yaml",
    "repos/proxy_ops_private/inventory/subscriptions.yaml",
)


@dataclass(frozen=True)
class PrivateTruthSyncAction:
    relative_path: str
    source_path: str
    target_path: str
    action: str
    source_digest: str
    target_digest: str | None


@dataclass(frozen=True)
class PrivateTruthSyncPlan:
    plan_id: str
    created_at: str
    runtime_workspace_root: str
    repo_root: str
    actions: tuple[PrivateTruthSyncAction, ...]
    status: str
    plan_path: Path
    plan_digest: str


@dataclass(frozen=True)
class PrivateTruthSyncApplyResult:
    plan_id: str
    updated_files: tuple[str, ...]
    audit_path: Path


def plan_private_truth_sync(
    *,
    runtime_workspace_root: str | Path,
    repo_root: str | Path,
    output_path: str | Path | None = None,
) -> PrivateTruthSyncPlan:
    resolved_runtime_root = Path(runtime_workspace_root).resolve()
    resolved_repo_root = Path(repo_root).resolve()
    created_at = _isoformat_now()
    plan_id = f"{_timestamp_token()}-private-truth-sync"
    actions: list[PrivateTruthSyncAction] = []

    for relative_path in TRUTH_SYNC_RELATIVE_PATHS:
        source_path = resolved_runtime_root / relative_path
        target_path = resolved_repo_root / relative_path
        if not source_path.exists():
            raise ValueError(f"runtime truth source is missing: {source_path}")
        source_digest = _sha256_file(source_path)
        target_digest = _sha256_file(target_path) if target_path.exists() else None
        if source_digest == target_digest:
            continue
        actions.append(
            PrivateTruthSyncAction(
                relative_path=relative_path,
                source_path=str(source_path),
                target_path=str(target_path),
                action="create" if target_digest is None else "update",
                source_digest=source_digest,
                target_digest=target_digest,
            )
        )

    plan_path = _resolve_plan_path(resolved_repo_root, plan_id, output_path)
    seed = PrivateTruthSyncPlan(
        plan_id=plan_id,
        created_at=created_at,
        runtime_workspace_root=str(resolved_runtime_root),
        repo_root=str(resolved_repo_root),
        actions=tuple(actions),
        status="planned",
        plan_path=plan_path,
        plan_digest="",
    )
    plan = _replace_plan_digest(seed)
    _write_plan(plan)
    return plan


def apply_private_truth_sync(
    *,
    plan: PrivateTruthSyncPlan,
    confirm: bool,
) -> PrivateTruthSyncApplyResult:
    if not confirm:
        raise ValueError("private truth sync requires explicit confirmation")
    if plan.status != "planned":
        raise ValueError("only planned private truth sync plans can be applied")
    if plan.plan_digest != _plan_digest(plan):
        raise ValueError("private truth sync plan digest mismatch")

    updated_files: list[str] = []
    for action in plan.actions:
        source_path = Path(action.source_path)
        target_path = Path(action.target_path)
        if not source_path.exists():
            raise ValueError(f"runtime truth source is missing: {source_path}")
        if _sha256_file(source_path) != action.source_digest:
            raise ValueError(f"runtime truth source changed since plan creation: {source_path}")
        current_target_digest = _sha256_file(target_path) if target_path.exists() else None
        if current_target_digest != action.target_digest:
            raise ValueError(f"target file changed since plan creation: {target_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        updated_files.append(action.relative_path)

    audit_path = _resolve_audit_path(Path(plan.repo_root), plan.plan_id)
    audit_payload = {
        "plan_id": plan.plan_id,
        "created_at": _isoformat_now(),
        "event": "applied",
        "updated_files": updated_files,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    applied_plan = PrivateTruthSyncPlan(
        plan_id=plan.plan_id,
        created_at=plan.created_at,
        runtime_workspace_root=plan.runtime_workspace_root,
        repo_root=plan.repo_root,
        actions=plan.actions,
        status="applied",
        plan_path=plan.plan_path,
        plan_digest="",
    )
    _write_plan(_replace_plan_digest(applied_plan))
    return PrivateTruthSyncApplyResult(
        plan_id=plan.plan_id,
        updated_files=tuple(updated_files),
        audit_path=audit_path,
    )


def load_private_truth_sync_plan(path: str | Path) -> PrivateTruthSyncPlan:
    resolved_path = Path(path).resolve()
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"failed to load private truth sync plan {resolved_path}: {exc}") from exc
    try:
        actions = tuple(
            PrivateTruthSyncAction(
                relative_path=str(item["relative_path"]),
                source_path=str(item["source_path"]),
                target_path=str(item["target_path"]),
                action=str(item["action"]),
                source_digest=str(item["source_digest"]),
                target_digest=str(item["target_digest"]) if item["target_digest"] is not None else None,
            )
            for item in payload["actions"]
        )
        plan = PrivateTruthSyncPlan(
            plan_id=str(payload["plan_id"]),
            created_at=str(payload["created_at"]),
            runtime_workspace_root=str(payload["runtime_workspace_root"]),
            repo_root=str(payload["repo_root"]),
            actions=actions,
            status=str(payload["status"]),
            plan_path=resolved_path,
            plan_digest=str(payload["plan_digest"]),
        )
    except KeyError as exc:
        raise ValueError(f"private truth sync plan is missing field {exc}") from exc
    return plan


def _replace_plan_digest(plan: PrivateTruthSyncPlan) -> PrivateTruthSyncPlan:
    return PrivateTruthSyncPlan(
        plan_id=plan.plan_id,
        created_at=plan.created_at,
        runtime_workspace_root=plan.runtime_workspace_root,
        repo_root=plan.repo_root,
        actions=plan.actions,
        status=plan.status,
        plan_path=plan.plan_path,
        plan_digest=_plan_digest(plan),
    )


def _write_plan(plan: PrivateTruthSyncPlan) -> None:
    plan.plan_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "plan_id": plan.plan_id,
        "created_at": plan.created_at,
        "runtime_workspace_root": plan.runtime_workspace_root,
        "repo_root": plan.repo_root,
        "actions": [asdict(item) for item in plan.actions],
        "status": plan.status,
        "plan_digest": plan.plan_digest,
    }
    plan.plan_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _plan_digest(plan: PrivateTruthSyncPlan) -> str:
    payload = {
        "plan_id": plan.plan_id,
        "created_at": plan.created_at,
        "runtime_workspace_root": plan.runtime_workspace_root,
        "repo_root": plan.repo_root,
        "actions": [asdict(item) for item in plan.actions],
        "status": plan.status,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _resolve_plan_path(repo_root: Path, plan_id: str, output_path: str | Path | None) -> Path:
    if output_path is not None:
        return Path(output_path).resolve()
    return repo_root / "state" / "private_truth_sync" / "plans" / f"{plan_id}.json"


def _resolve_audit_path(repo_root: Path, plan_id: str) -> Path:
    return repo_root / "state" / "private_truth_sync" / "audit" / f"{plan_id}-applied.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _isoformat_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
