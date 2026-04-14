from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


VALID_OBSERVED_STATUSES = ("healthy", "degraded", "down", "unknown")


class StateFileError(ValueError):
    """Raised when a platform state file is invalid."""


@dataclass(frozen=True)
class HostRecord:
    host_id: str
    display_name: str
    endpoint: str
    provider: str
    enabled: bool
    include_in_subscription: bool
    tags: tuple[str, ...]


@dataclass(frozen=True)
class HostRegistry:
    hosts: tuple[HostRecord, ...]
    source_path: Path

    def by_id(self) -> dict[str, HostRecord]:
        return {host.host_id: host for host in self.hosts}


@dataclass(frozen=True)
class HostObservation:
    host_id: str
    status: str
    source: str
    observed_at: str | None
    detail: str | None


@dataclass(frozen=True)
class HostObservationSnapshot:
    observations: tuple[HostObservation, ...]
    source_path: Path

    def by_host_id(self) -> dict[str, HostObservation]:
        latest_by_host: dict[str, HostObservation] = {}
        for observation in self.observations:
            latest_by_host[observation.host_id] = observation
        return latest_by_host


@dataclass(frozen=True)
class HostView:
    host_id: str
    display_name: str
    provider: str
    endpoint: str
    desired_state: str
    observed_status: str
    observation_source: str
    subscription_included: bool
    subscription_reason: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class SubscriptionMember:
    host_id: str
    display_name: str
    provider: str
    endpoint: str
    observed_status: str
    reason: str


@dataclass(frozen=True)
class SubscriptionProjection:
    members: tuple[SubscriptionMember, ...]
    excluded_host_ids: tuple[str, ...]
    unknown_observation_host_ids: tuple[str, ...]


def load_host_registry(path: str | Path) -> HostRegistry:
    source_path = Path(path).resolve()
    payload = _load_yaml_mapping(source_path)
    hosts_payload = payload.get("hosts")
    if not isinstance(hosts_payload, list):
        raise StateFileError(f"{source_path} must define a hosts list")
    hosts: list[HostRecord] = []
    seen_ids: set[str] = set()
    for item in hosts_payload:
        host_id = str(item["host_id"])
        if host_id in seen_ids:
            raise StateFileError(f"duplicate host_id {host_id!r} in {source_path}")
        seen_ids.add(host_id)
        hosts.append(
            HostRecord(
                host_id=host_id,
                display_name=str(item["display_name"]),
                endpoint=str(item["endpoint"]),
                provider=str(item["provider"]),
                enabled=bool(item.get("enabled", True)),
                include_in_subscription=bool(item.get("include_in_subscription", True)),
                tags=tuple(str(value) for value in item.get("tags", [])),
            )
        )
    return HostRegistry(hosts=tuple(hosts), source_path=source_path)


def load_host_observations(path: str | Path) -> HostObservationSnapshot:
    source_path = Path(path).resolve()
    payload = _load_yaml_mapping(source_path)
    observations_payload = payload.get("observations")
    if not isinstance(observations_payload, list):
        raise StateFileError(f"{source_path} must define an observations list")
    observations: list[HostObservation] = []
    for item in observations_payload:
        status = str(item["status"])
        if status not in VALID_OBSERVED_STATUSES:
            raise StateFileError(
                f"observation status {status!r} in {source_path} must be one of {VALID_OBSERVED_STATUSES!r}"
            )
        observations.append(
            HostObservation(
                host_id=str(item["host_id"]),
                status=status,
                source=str(item.get("source", "unknown")),
                observed_at=str(item["observed_at"]) if item.get("observed_at") else None,
                detail=str(item["detail"]) if item.get("detail") else None,
            )
        )
    return HostObservationSnapshot(observations=tuple(observations), source_path=source_path)


def build_host_views(
    registry: HostRegistry,
    observations: HostObservationSnapshot | None = None,
) -> tuple[HostView, ...]:
    observation_by_host = observations.by_host_id() if observations else {}
    views: list[HostView] = []
    for host in registry.hosts:
        observation = observation_by_host.get(host.host_id)
        observed_status = observation.status if observation else "unknown"
        observation_source = observation.source if observation else "none"
        desired_state = "enabled" if host.enabled else "disabled"
        subscription_included = host.enabled and host.include_in_subscription
        subscription_reason = _subscription_reason(host)
        views.append(
            HostView(
                host_id=host.host_id,
                display_name=host.display_name,
                provider=host.provider,
                endpoint=host.endpoint,
                desired_state=desired_state,
                observed_status=observed_status,
                observation_source=observation_source,
                subscription_included=subscription_included,
                subscription_reason=subscription_reason,
                tags=host.tags,
            )
        )
    return tuple(views)


def project_subscription(
    registry: HostRegistry,
    observations: HostObservationSnapshot | None = None,
) -> SubscriptionProjection:
    views = build_host_views(registry, observations)
    members = tuple(
        SubscriptionMember(
            host_id=view.host_id,
            display_name=view.display_name,
            provider=view.provider,
            endpoint=view.endpoint,
            observed_status=view.observed_status,
            reason=view.subscription_reason,
        )
        for view in views
        if view.subscription_included
    )
    excluded = tuple(view.host_id for view in views if not view.subscription_included)
    unknown_ids: tuple[str, ...] = ()
    if observations:
        registry_ids = {host.host_id for host in registry.hosts}
        unknown_ids = tuple(
            observation.host_id
            for observation in observations.observations
            if observation.host_id not in registry_ids
        )
    return SubscriptionProjection(
        members=members,
        excluded_host_ids=excluded,
        unknown_observation_host_ids=unknown_ids,
    )


def _subscription_reason(host: HostRecord) -> str:
    if not host.enabled:
        return "excluded: disabled in registry"
    if not host.include_in_subscription:
        return "excluded: registry marks host as out of subscription"
    return "included: registry enabled host for subscription"


def _load_yaml_mapping(path: Path) -> dict[str, object]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise StateFileError(f"failed to load state file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StateFileError(f"{path} must contain a YAML mapping")
    return payload
