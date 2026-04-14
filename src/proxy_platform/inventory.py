from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from proxy_platform.manifest import HostRegistrySource


@dataclass(frozen=True)
class HostRecord:
    name: str
    host: str
    ssh_port: int
    base_port: int
    subscription_alias: str
    enabled: bool
    include_in_subscription: bool
    infra_core_candidate: bool
    change_policy: str
    provider: str
    deployment_topology: str
    runtime_service: str


@dataclass(frozen=True)
class SubscriptionSettings:
    profile_name: str
    subscription_base_url: str
    hiddify_fragment_name: str
    remote_profile_name: str
    update_interval_hours: int


@dataclass(frozen=True)
class ObservedHostState:
    name: str
    health: str
    source: str
    observed_at: str
    detail: str | None


@dataclass(frozen=True)
class HostRegistry:
    nodes: list[HostRecord]
    subscriptions: SubscriptionSettings
    observations: dict[str, ObservedHostState]


def load_host_registry(source: HostRegistrySource, workspace_root: str | Path) -> HostRegistry:
    root = Path(workspace_root).resolve()
    inventory_payload = _load_mapping(_resolve_source_path(root, source.inventory_path))
    subscriptions_payload = _load_mapping(_resolve_source_path(root, source.subscriptions_path))
    observations_payload: dict[str, Any] = {}
    if source.observations_path is not None:
        observations_path = _resolve_source_path(root, source.observations_path)
        if observations_path.exists():
            observations_payload = _load_mapping(observations_path)

    nodes = [_host_record_from_mapping(item) for item in inventory_payload.get("nodes", [])]
    subscriptions = SubscriptionSettings(
        profile_name=str(subscriptions_payload["profile_name"]),
        subscription_base_url=str(subscriptions_payload["subscription_base_url"]),
        hiddify_fragment_name=str(subscriptions_payload["hiddify_fragment_name"]),
        remote_profile_name=str(subscriptions_payload["remote_profile_name"]),
        update_interval_hours=int(subscriptions_payload["update_interval_hours"]),
    )
    observations = {
        item["name"]: ObservedHostState(
            name=str(item["name"]),
            health=str(item["health"]),
            source=str(item["source"]),
            observed_at=str(item["observed_at"]),
            detail=str(item["detail"]) if item.get("detail") else None,
        )
        for item in observations_payload.get("hosts", [])
    }
    return HostRegistry(nodes=nodes, subscriptions=subscriptions, observations=observations)


def add_host_record(source: HostRegistrySource, workspace_root: str | Path, payload: dict[str, Any]) -> HostRecord:
    root = Path(workspace_root).resolve()
    inventory_path = _resolve_source_path(root, source.inventory_path)
    inventory_payload = _load_mapping(inventory_path)
    nodes = list(inventory_payload.get("nodes", []))
    record = _host_record_from_mapping(payload)
    if any(item["name"] == record.name for item in nodes):
        raise ValueError(f"host already exists: {record.name}")
    nodes.append(asdict(record))
    inventory_payload["nodes"] = nodes
    _write_mapping_as_yaml(inventory_path, inventory_payload)
    return record


def remove_host_record(source: HostRegistrySource, workspace_root: str | Path, host_name: str) -> str:
    root = Path(workspace_root).resolve()
    inventory_path = _resolve_source_path(root, source.inventory_path)
    inventory_payload = _load_mapping(inventory_path)
    nodes = list(inventory_payload.get("nodes", []))
    remaining = [item for item in nodes if item["name"] != host_name]
    if len(remaining) == len(nodes):
        raise KeyError(host_name)
    inventory_payload["nodes"] = remaining
    _write_mapping_as_yaml(inventory_path, inventory_payload)
    return host_name


def _resolve_source_path(workspace_root: Path, source_path: Path) -> Path:
    return source_path if source_path.is_absolute() else workspace_root / source_path


def _load_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping")
    return payload


def _write_mapping_as_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _host_record_from_mapping(payload: dict[str, Any]) -> HostRecord:
    return HostRecord(
        name=str(payload["name"]),
        host=str(payload["host"]),
        ssh_port=int(payload["ssh_port"]),
        base_port=int(payload["base_port"]),
        subscription_alias=str(payload["subscription_alias"]),
        enabled=bool(payload["enabled"]),
        include_in_subscription=bool(payload.get("include_in_subscription", True)),
        infra_core_candidate=bool(payload["infra_core_candidate"]),
        change_policy=str(payload["change_policy"]),
        provider=str(payload["provider"]),
        deployment_topology=str(payload.get("deployment_topology", "unknown")),
        runtime_service=str(payload.get("runtime_service", "unknown")),
    )
