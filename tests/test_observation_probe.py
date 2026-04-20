from __future__ import annotations

import json
from pathlib import Path

from proxy_platform.manifest import HostRegistrySource
from proxy_platform.observation_probe import refresh_host_observations


def _write_inventory_fixture(root: Path) -> HostRegistrySource:
    inventory_dir = root / "operator"
    inventory_dir.mkdir(parents=True, exist_ok=True)
    (inventory_dir / "nodes.yaml").write_text(
        """
nodes:
  - name: lisahost
    host: 38.34.8.59
    ssh_port: 27823
    base_port: 10000
    subscription_alias: GG-Lisa-Stable
    enabled: true
    include_in_subscription: true
    infra_core_candidate: true
    change_policy: frozen
    provider: Lisahost
    deployment_topology: standalone_vps
    runtime_service: cliproxy-plus
  - name: vmrack1
    host: 38.65.93.39
    ssh_port: 22
    base_port: 10000
    subscription_alias: GG-Vmrack1
    enabled: true
    include_in_subscription: true
    infra_core_candidate: true
    change_policy: mutable
    provider: VMRack
    deployment_topology: standalone_vps
    runtime_service: cliproxy-plus
""",
        encoding="utf-8",
    )
    (inventory_dir / "subscriptions.yaml").write_text(
        """
profile_name: GG Proxy Nodes
subscription_base_url: https://example.com/subscriptions
hiddify_fragment_name: GG Proxy Nodes
remote_profile_name: GG Proxy Nodes Remote
update_interval_hours: 12
""",
        encoding="utf-8",
    )
    return HostRegistrySource(
        inventory_path=Path("operator/nodes.yaml"),
        subscriptions_path=Path("operator/subscriptions.yaml"),
        observations_path=Path("state/observations/hosts.json"),
        required_modes=["operator"],
    )


def test_refresh_host_observations_writes_tcp_probe_results(monkeypatch, tmp_path: Path) -> None:
    source = _write_inventory_fixture(tmp_path)
    attempted_targets: list[tuple[str, int, float]] = []

    class _FakeConnection:
        def close(self) -> None:
            return None

    def fake_create_connection(target: tuple[str, int], timeout: float):
        attempted_targets.append((target[0], target[1], timeout))
        if target[0] == "38.34.8.59":
            raise ConnectionRefusedError("refused")
        return _FakeConnection()

    monkeypatch.setattr("proxy_platform.observation_probe.socket.create_connection", fake_create_connection)

    result = refresh_host_observations(
        source=source,
        workspace_root=tmp_path,
        connect_timeout_seconds=1.5,
    )

    assert result.probed_hosts == 2
    assert result.healthy_hosts == 1
    assert result.down_hosts == 1
    assert attempted_targets == [
        ("38.34.8.59", 10001, 1.5),
        ("38.65.93.39", 10001, 1.5),
    ]

    payload = json.loads((tmp_path / "state" / "observations" / "hosts.json").read_text(encoding="utf-8"))
    assert payload["hosts"][0]["name"] == "lisahost"
    assert payload["hosts"][0]["health"] == "down"
    assert payload["hosts"][0]["source"] == "tcp_probe"
    assert "10001" in payload["hosts"][0]["detail"]
    assert payload["hosts"][1]["name"] == "vmrack1"
    assert payload["hosts"][1]["health"] == "healthy"
    assert payload["hosts"][1]["source"] == "tcp_probe"
