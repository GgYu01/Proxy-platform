from pathlib import Path

from fastapi.testclient import TestClient

from proxy_platform.web_app import create_app


def _write_fixture(tmp_path: Path) -> Path:
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
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public, operator]
repos: []
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    observations_path: state/observed/hosts.json
    required_modes: [operator]
  local_providers:
    - id: local_mcp_pool
      display_name: Local MCP pool
      kind: mcp
      startup_timeout_seconds: 15
      request_timeout_seconds: 45
      startup_max_attempts: 3
      request_max_attempts: 2
commands: {}
""",
        encoding="utf-8",
    )
    return manifest_path


def test_web_app_returns_hosts_subscriptions_and_html(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    hosts_response = client.get("/api/hosts")
    assert hosts_response.status_code == 200
    assert hosts_response.json()["hosts"][0]["name"] == "lisahost"
    assert hosts_response.json()["hosts"][0]["observed_health"] == "healthy"

    subscriptions_response = client.get("/api/subscriptions")
    assert subscriptions_response.status_code == 200
    assert subscriptions_response.json()["multi_node_url"] == "https://example.com/subscriptions/v2ray_nodes.txt"

    html_response = client.get("/")
    assert html_response.status_code == 200
    assert "lisahost" in html_response.text
    assert "https://example.com/subscriptions/v2ray_nodes.txt" in html_response.text


def test_web_app_can_add_and_remove_hosts_in_inventory_file(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    add_response = client.post(
        "/api/hosts",
        json={
            "name": "vmrack1",
            "host": "38.65.93.39",
            "ssh_port": 22,
            "base_port": 10000,
            "subscription_alias": "GG-Vmrack1",
            "enabled": True,
            "infra_core_candidate": True,
            "change_policy": "mutable",
            "provider": "vmrack",
        },
    )
    assert add_response.status_code == 200
    assert add_response.json()["host"]["name"] == "vmrack1"

    delete_response = client.delete("/api/hosts/vmrack1")
    assert delete_response.status_code == 200
    assert delete_response.json()["removed"] == "vmrack1"


def test_web_app_rejects_public_mode_when_host_registry_is_private(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path))

    response = client.get("/api/hosts")

    assert response.status_code == 500
    assert response.json()["detail"] == "host registry source is not configured for mode public"
