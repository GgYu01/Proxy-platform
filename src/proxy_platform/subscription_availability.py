from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

DEFAULT_EXCLUDE_AFTER_HOURS = 72
DEFAULT_LEDGER_RELATIVE = "state/node_availability.json"
PROXY_OPS_PRIVATE_RELATIVE = Path("repos") / "proxy_ops_private"


@dataclass(frozen=True)
class AvailabilityPolicyView:
    exclude_after_hours: int
    ledger_path: Path


@dataclass(frozen=True)
class AvailabilityContext:
    policy: AvailabilityPolicyView | None
    ledger_nodes: dict[str, Any]


@dataclass(frozen=True)
class NodeAvailabilityView:
    status: str
    unavailable_since: str | None
    publish_reason: str


def load_availability_context(workspace_root: str | Path) -> AvailabilityContext:
    repo_root = Path(workspace_root).resolve() / PROXY_OPS_PRIVATE_RELATIVE
    subscriptions_path = repo_root / "inventory" / "subscriptions.yaml"
    if not subscriptions_path.exists():
        return AvailabilityContext(policy=None, ledger_nodes={})

    policy_payload = yaml.safe_load(subscriptions_path.read_text(encoding="utf-8")) or {}
    availability_policy = policy_payload.get("availability_policy") or {}
    ledger_relative = str(availability_policy.get("ledger_path") or DEFAULT_LEDGER_RELATIVE)
    policy = AvailabilityPolicyView(
        exclude_after_hours=int(availability_policy.get("exclude_after_hours", DEFAULT_EXCLUDE_AFTER_HOURS)),
        ledger_path=repo_root / ledger_relative,
    )
    ledger_nodes: dict[str, Any] = {}
    if policy.ledger_path.exists():
        payload = json.loads(policy.ledger_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            ledger_nodes = dict(payload.get("nodes") or {})
    return AvailabilityContext(policy=policy, ledger_nodes=ledger_nodes)


def evaluate_node_availability(
    *,
    node_name: str,
    subscription_availability_exempt: bool,
    registry_publishable: bool,
    context: AvailabilityContext | None,
    now: datetime | None = None,
) -> NodeAvailabilityView:
    if not registry_publishable:
        return NodeAvailabilityView(
            status="registry_excluded",
            unavailable_since=None,
            publish_reason=_registry_publish_reason(registry_publishable=False),
        )
    if subscription_availability_exempt:
        return NodeAvailabilityView(
            status="exempt",
            unavailable_since=None,
            publish_reason="enabled_in_registry",
        )
    if context is None or context.policy is None:
        return NodeAvailabilityView(
            status="unknown",
            unavailable_since=None,
            publish_reason="enabled_in_registry",
        )

    entry = context.ledger_nodes.get(node_name)
    if not entry or not entry.get("unavailable_since"):
        return NodeAvailabilityView(
            status="unknown" if not entry else "included",
            unavailable_since=None,
            publish_reason="enabled_in_registry",
        )

    unavailable_since = str(entry["unavailable_since"])
    now = now or _utc_now()
    age = now - _parse_iso(unavailable_since)
    if age >= timedelta(hours=context.policy.exclude_after_hours):
        return NodeAvailabilityView(
            status="excluded",
            unavailable_since=unavailable_since,
            publish_reason="auto_excluded_unavailable_72h",
        )
    return NodeAvailabilityView(
        status="pending",
        unavailable_since=unavailable_since,
        publish_reason="included_pending_availability",
    )


def is_subscription_eligible(
    *,
    node_name: str,
    subscription_availability_exempt: bool,
    context: AvailabilityContext | None,
    now: datetime | None = None,
) -> bool:
    if subscription_availability_exempt:
        return True
    if context is None or context.policy is None:
        return True
    entry = context.ledger_nodes.get(node_name)
    if not entry or not entry.get("unavailable_since"):
        return True
    now = now or _utc_now()
    unavailable_since = _parse_iso(str(entry["unavailable_since"]))
    return now - unavailable_since < timedelta(hours=context.policy.exclude_after_hours)


def update_availability_ledger_from_probe_hosts(
    workspace_root: str | Path,
    probe_hosts: list[dict[str, str]],
    *,
    now: datetime | None = None,
) -> Path | None:
    context = load_availability_context(workspace_root)
    if context.policy is None:
        return None

    now = now or _utc_now()
    payload = {"updated_at": _isoformat(now), "nodes": dict(context.ledger_nodes)}
    nodes: dict[str, Any] = payload["nodes"]
    for item in probe_hosts:
        name = str(item["name"])
        previous = nodes.get(name) or {}
        observed_at = str(item.get("observed_at") or _isoformat(now))
        if str(item.get("health")) == "healthy":
            nodes[name] = {
                "last_probe_at": observed_at,
                "last_health": "healthy",
                "unavailable_since": None,
                "last_success_at": observed_at,
                "detail": item.get("detail"),
            }
            continue
        unavailable_since = previous.get("unavailable_since") or observed_at
        nodes[name] = {
            "last_probe_at": observed_at,
            "last_health": "down",
            "unavailable_since": unavailable_since,
            "last_success_at": previous.get("last_success_at"),
            "detail": item.get("detail"),
        }

    ledger_path = context.policy.ledger_path
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ledger_path


def _registry_publish_reason(*, registry_publishable: bool) -> str:
    if registry_publishable:
        return "enabled_in_registry"
    return "disabled_in_registry"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
