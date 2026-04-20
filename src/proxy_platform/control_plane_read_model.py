from __future__ import annotations

import base64
import json
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ControlPlaneReadError(RuntimeError):
    """Raised when the authoritative control-plane read model cannot be loaded."""


class ControlPlaneReadClient(Protocol):
    def fetch_worker_quotas(self) -> dict[str, Any]:
        """Return a read-only worker/oauth quota snapshot."""


class HttpControlPlaneReadClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        self._authorization_header = f"Basic {token}"

    def fetch_worker_quotas(self) -> dict[str, Any]:
        accounts_payload = self._request_json("/api/accounts/latest-view")
        overview_payload = self._request_json("/api/tactical-stats/overview")
        return build_worker_quota_snapshot(accounts_payload, overview_payload)

    def _request_json(self, path: str) -> Any:
        request = Request(
            f"{self._base_url}{path}",
            headers={
                "Accept": "application/json",
                "Authorization": self._authorization_header,
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise ControlPlaneReadError(
                f"control-plane read failed for {path}: http {exc.code} {detail or exc.reason}"
            ) from exc
        except URLError as exc:
            raise ControlPlaneReadError(f"control-plane read failed for {path}: {exc.reason}") from exc
        except OSError as exc:
            raise ControlPlaneReadError(f"control-plane read failed for {path}: {exc}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ControlPlaneReadError(
                f"control-plane read failed for {path}: response was not valid JSON"
            ) from exc


def build_worker_quota_snapshot(accounts_payload: Any, overview_payload: Any) -> dict[str, Any]:
    if not isinstance(accounts_payload, list):
        raise ControlPlaneReadError("control-plane accounts latest-view must return a JSON array")
    if not isinstance(overview_payload, Mapping):
        raise ControlPlaneReadError("control-plane tactical overview must return a JSON object")

    overview_workers_raw = overview_payload.get("workers")
    if overview_workers_raw is None:
        overview_workers: list[Mapping[str, Any]] = []
    elif isinstance(overview_workers_raw, list):
        overview_workers = [item for item in overview_workers_raw if isinstance(item, Mapping)]
    else:
        raise ControlPlaneReadError("control-plane tactical overview workers must be a JSON array")

    worker_order: list[str] = []
    worker_status_by_id: dict[str, str] = {}
    worker_captured_at_by_id: dict[str, str | None] = {}
    for item in overview_workers:
        worker_id = _string_or_none(item.get("worker_id"))
        if not worker_id:
            continue
        worker_order.append(worker_id)
        worker_status_by_id[worker_id] = _string_or_default(item.get("status"), "unknown")
        worker_captured_at_by_id[worker_id] = _string_or_none(item.get("captured_at"))

    accounts_by_worker: dict[str, list[dict[str, Any]]] = {}
    group_ids_by_worker: dict[str, set[str]] = {}
    for raw_account in accounts_payload:
        if not isinstance(raw_account, Mapping):
            raise ControlPlaneReadError("control-plane accounts latest-view must contain JSON objects")
        worker_id = _string_or_default(raw_account.get("worker_id"), "unknown")
        normalized_account = _normalize_account(raw_account)
        accounts_by_worker.setdefault(worker_id, []).append(normalized_account)
        group_id = normalized_account["group_id"]
        if group_id:
            group_ids_by_worker.setdefault(worker_id, set()).add(group_id)
        if worker_id not in worker_status_by_id:
            worker_status_by_id[worker_id] = "unknown"
            worker_captured_at_by_id[worker_id] = normalized_account["probe_observed_at"]

    ordered_worker_ids = list(dict.fromkeys(worker_order + sorted(accounts_by_worker.keys())))
    workers: list[dict[str, Any]] = []
    accounts_with_snapshot = 0
    accounts_without_snapshot = 0
    fresh_probe_failures = 0

    for worker_id in ordered_worker_ids:
        accounts = sorted(
            accounts_by_worker.get(worker_id, []),
            key=lambda item: (item["auth_name"], item["account_id"]),
        )
        worker_accounts_with_snapshot = sum(1 for item in accounts if item["latest_snapshot_present"])
        worker_accounts_without_snapshot = len(accounts) - worker_accounts_with_snapshot
        worker_fresh_probe_failures = sum(1 for item in accounts if item["has_fresh_probe_failure"])
        accounts_with_snapshot += worker_accounts_with_snapshot
        accounts_without_snapshot += worker_accounts_without_snapshot
        fresh_probe_failures += worker_fresh_probe_failures

        workers.append(
            {
                "worker_id": worker_id,
                "status": worker_status_by_id.get(worker_id, "unknown"),
                "captured_at": worker_captured_at_by_id.get(worker_id),
                "group_ids": sorted(group_ids_by_worker.get(worker_id, set())),
                "account_total": len(accounts),
                "accounts_with_snapshot": worker_accounts_with_snapshot,
                "accounts_without_snapshot": worker_accounts_without_snapshot,
                "fresh_probe_failures": worker_fresh_probe_failures,
                "accounts": accounts,
            }
        )

    captured_at = _string_or_none(overview_payload.get("captured_at"))
    if captured_at is None:
        worker_captured_at_values = [item["captured_at"] for item in workers if item.get("captured_at")]
        captured_at = max(worker_captured_at_values) if worker_captured_at_values else None

    return {
        "meta": {
            "captured_at": captured_at,
            "worker_total": len(workers),
            "worker_realtime": sum(1 for item in workers if item["status"] == "realtime"),
            "worker_fallback": sum(1 for item in workers if item["status"] == "fallback"),
            "worker_failed": sum(1 for item in workers if item["status"] == "failed"),
            "account_total": sum(item["account_total"] for item in workers),
            "accounts_with_snapshot": accounts_with_snapshot,
            "accounts_without_snapshot": accounts_without_snapshot,
            "fresh_probe_failures": fresh_probe_failures,
        },
        "workers": workers,
    }


def _normalize_account(item: Mapping[str, Any]) -> dict[str, Any]:
    probe_state = item.get("probe_state") if isinstance(item.get("probe_state"), Mapping) else {}
    latest_snapshot = (
        item.get("latest_snapshot") if isinstance(item.get("latest_snapshot"), Mapping) else None
    )
    probe_status = _string_or_none(probe_state.get("status")) or _string_or_default(
        item.get("last_probe_status"),
        "unknown",
    )
    has_fresh_probe_failure = bool(probe_state.get("has_fresh_failure")) or probe_status == "error"
    quota_summary = (
        _string_or_none(latest_snapshot.get("summary_value"))
        or _string_or_none(latest_snapshot.get("normalized_remaining_value"))
        or "无最新配额快照"
    )
    reset_at = _string_or_none(latest_snapshot.get("normalized_reset_at")) or _string_or_none(
        latest_snapshot.get("expires_at")
    )
    return {
        "account_id": _string_or_default(item.get("account_id"), ""),
        "group_id": _string_or_default(item.get("group_id"), ""),
        "provider": _string_or_default(item.get("provider"), "unknown"),
        "auth_name": _string_or_default(item.get("auth_name"), "(missing auth file name)"),
        "email": _string_or_none(item.get("email")),
        "account_status": _string_or_default(item.get("status"), "unknown"),
        "probe_status": probe_status,
        "probe_message": _string_or_none(probe_state.get("message")),
        "probe_observed_at": _string_or_none(probe_state.get("observed_at"))
        or _string_or_none(item.get("last_probe_at")),
        "has_fresh_probe_failure": has_fresh_probe_failure,
        "latest_snapshot_present": latest_snapshot is not None,
        "quota_summary": quota_summary,
        "reset_at": reset_at,
        "capability_level": _string_or_default(
            latest_snapshot.get("capability_level") if latest_snapshot else None,
            "unavailable",
        ),
        "source_endpoint": _string_or_none(latest_snapshot.get("source_endpoint") if latest_snapshot else None),
    }


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_or_default(value: Any, default: str) -> str:
    resolved = _string_or_none(value)
    return resolved if resolved is not None else default
