from pathlib import Path

from proxy_platform.inventory import load_host_registry
from proxy_platform.manifest import HostRegistrySource
from proxy_platform.projections import build_host_views, build_subscription_projection


def _write_registry_fixture(tmp_path: Path) -> HostRegistrySource:
    operator_dir = tmp_path / "operator"
    observed_dir = tmp_path / "state" / "observed"
    operator_dir.mkdir(parents=True)
    observed_dir.mkdir(parents=True)
    (operator_dir / "nodes.yaml").write_text(
        """
nodes:
  - name: lisahost
    host: 38.34.8.59
    ssh_port: 27823
    base_port: 10000
    subscription_alias: GG-Lisa-Stable
    enabled: true
    infra_core_candidate: true
    change_policy: frozen
    provider: Lisahost
  - name: vmrack1
    host: 38.65.93.39
    ssh_port: 22
    base_port: 10000
    subscription_alias: GG-Vmrack1
    enabled: false
    infra_core_candidate: true
    change_policy: mutable
    provider: vmrack
""",
        encoding="utf-8",
    )
    (operator_dir / "subscriptions.yaml").write_text(
        """
profile_name: GG Proxy Nodes
subscription_base_url: https://example.com/subscriptions
hiddify_fragment_name: GG Proxy Nodes
remote_profile_name: GG Proxy Nodes Remote
update_interval_hours: 12
""",
        encoding="utf-8",
    )
    (observed_dir / "hosts.json").write_text(
        """
hosts:
  - name: lisahost
    health: healthy
    source: remote_probe
    observed_at: 2026-04-14T10:00:00Z
    detail: podman active
  - name: vmrack1
    health: down
    source: remote_probe
    observed_at: 2026-04-14T10:01:00Z
    detail: connection timeout
""",
        encoding="utf-8",
    )
    return HostRegistrySource(
        inventory_path=Path("operator/nodes.yaml"),
        subscriptions_path=Path("operator/subscriptions.yaml"),
        observations_path=Path("state/observed/hosts.json"),
    )


def test_build_host_views_keeps_disabled_hosts_visible_but_not_publishable(tmp_path: Path) -> None:
    source = _write_registry_fixture(tmp_path)
    registry = load_host_registry(source, tmp_path)

    views = {view.name: view for view in build_host_views(registry)}

    assert views["lisahost"].observed_health == "healthy"
    assert views["lisahost"].should_publish is True
    assert views["vmrack1"].observed_health == "down"
    assert views["vmrack1"].should_publish is False
    assert views["vmrack1"].publish_reason == "disabled_in_registry"


def test_build_subscription_projection_only_emits_enabled_nodes(tmp_path: Path) -> None:
    source = _write_registry_fixture(tmp_path)
    registry = load_host_registry(source, tmp_path)

    projection = build_subscription_projection(registry)

    assert projection.multi_node_url == "https://example.com/subscriptions/v2ray_nodes.txt"
    assert projection.multi_node_hiddify_import == (
        "hiddify://import/https://example.com/subscriptions/v2ray_nodes.txt#GG%20Proxy%20Nodes"
    )
    assert [item.name for item in projection.per_node] == ["lisahost"]
    assert projection.per_node[0].v2ray_url == "https://example.com/subscriptions/v2ray_node_lisahost.txt"

