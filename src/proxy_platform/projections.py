from __future__ import annotations

from dataclasses import dataclass
import urllib.parse

from proxy_platform.inventory import HostRegistry


@dataclass(frozen=True)
class HostView:
    name: str
    host: str
    ssh_port: int
    provider: str
    change_policy: str
    enabled: bool
    observed_health: str
    observed_source: str | None
    observed_at: str | None
    observed_detail: str | None
    should_publish: bool
    publish_reason: str


@dataclass(frozen=True)
class NodeSubscriptionProjection:
    name: str
    alias: str
    v2ray_url: str
    hiddify_import_url: str


@dataclass(frozen=True)
class SubscriptionProjection:
    multi_node_url: str
    multi_node_hiddify_import: str
    remote_profile_url: str
    per_node: list[NodeSubscriptionProjection]


def build_host_views(registry: HostRegistry) -> list[HostView]:
    views: list[HostView] = []
    for node in registry.nodes:
        observed = registry.observations.get(node.name)
        should_publish = node.enabled
        views.append(
            HostView(
                name=node.name,
                host=node.host,
                ssh_port=node.ssh_port,
                provider=node.provider,
                change_policy=node.change_policy,
                enabled=node.enabled,
                observed_health=observed.health if observed else "unknown",
                observed_source=observed.source if observed else None,
                observed_at=observed.observed_at if observed else None,
                observed_detail=observed.detail if observed else None,
                should_publish=should_publish,
                publish_reason="enabled_in_registry" if should_publish else "disabled_in_registry",
            )
        )
    return views


def build_subscription_projection(registry: HostRegistry) -> SubscriptionProjection:
    base_url = registry.subscriptions.subscription_base_url.rstrip("/")
    multi_node_url = base_url + "/v2ray_nodes.txt"
    per_node: list[NodeSubscriptionProjection] = []
    for node in registry.nodes:
        if not node.enabled:
            continue
        v2ray_url = base_url + f"/v2ray_node_{node.name}.txt"
        per_node.append(
            NodeSubscriptionProjection(
                name=node.name,
                alias=node.subscription_alias,
                v2ray_url=v2ray_url,
                hiddify_import_url=_hiddify_import(v2ray_url, node.subscription_alias),
            )
        )
    return SubscriptionProjection(
        multi_node_url=multi_node_url,
        multi_node_hiddify_import=_hiddify_import(multi_node_url, registry.subscriptions.hiddify_fragment_name),
        remote_profile_url=base_url + "/singbox-client-profile.json",
        per_node=per_node,
    )


def _hiddify_import(url: str, fragment: str) -> str:
    return f"hiddify://import/{url}#{urllib.parse.quote(fragment)}"
