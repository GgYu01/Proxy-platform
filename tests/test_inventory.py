from pathlib import Path

from proxy_platform.inventory import load_host_registry
from proxy_platform.manifest import HostRegistrySource


def test_load_host_registry_merges_inventory_subscriptions_and_observations(tmp_path: Path) -> None:
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
""",
        encoding="utf-8",
    )

    registry = load_host_registry(
        HostRegistrySource(
            inventory_path=Path("operator/nodes.yaml"),
            subscriptions_path=Path("operator/subscriptions.yaml"),
            observations_path=Path("state/observed/hosts.json"),
        ),
        tmp_path,
    )

    assert [node.name for node in registry.nodes] == ["lisahost", "vmrack1"]
    assert registry.subscriptions.subscription_base_url == "https://example.com/subscriptions"
    assert registry.observations["lisahost"].health == "healthy"
    assert registry.observations["lisahost"].source == "remote_probe"

