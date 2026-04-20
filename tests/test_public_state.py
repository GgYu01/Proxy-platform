from pathlib import Path
import json

import pytest

from proxy_platform.manifest import load_manifest
from proxy_platform.private_sync import apply_private_truth_sync
from proxy_platform.private_sync import plan_private_truth_sync
from proxy_platform.public_state import export_public_state
from proxy_platform.public_state import load_public_host_console


def _write_operator_fixture(root: Path) -> Path:
    operator_dir = root / "operator"
    observed_dir = root / "state" / "observed"
    operator_dir.mkdir(parents=True, exist_ok=True)
    observed_dir.mkdir(parents=True, exist_ok=True)
    (operator_dir / "nodes.yaml").write_text(
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
    manifest_path = root / "platform.manifest.yaml"
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
commands: {}
state_sources:
  - id: host_registry
    display_name: Host Registry
    description: operator truth
    kind: host_registry
    repo_id: proxy-platform
    path: operator/nodes.yaml
    ownership: private_truth
    required_modes: [operator]
  - id: subscription_policy
    display_name: Subscription Policy
    description: operator truth
    kind: subscription_policy
    repo_id: proxy-platform
    path: operator/subscriptions.yaml
    ownership: private_truth
    required_modes: [operator]
  - id: host_observation
    display_name: Host Observation
    description: observed state
    kind: host_observation
    repo_id: proxy-platform
    path: state/observed/hosts.json
    ownership: platform_observed_state
    required_modes: [operator]
""",
        encoding="utf-8",
    )
    return manifest_path


def test_export_public_state_writes_sanitized_snapshots(tmp_path: Path) -> None:
    manifest_path = _write_operator_fixture(tmp_path)
    manifest = load_manifest(manifest_path)

    result = export_public_state(
        manifest=manifest,
        workspace_root=tmp_path,
        output_root=tmp_path / "state" / "public",
    )

    host_snapshot = json.loads(result.host_console_path.read_text(encoding="utf-8"))
    subscription_snapshot = json.loads(result.subscription_path.read_text(encoding="utf-8"))

    assert host_snapshot["hosts"][0]["name"] == "lisahost"
    assert "host" not in host_snapshot["hosts"][0]
    assert "ssh_port" not in host_snapshot["hosts"][0]
    assert host_snapshot["hosts"][0]["observed_health"] == "healthy"
    assert subscription_snapshot["multi_node_url"] == "https://example.com/subscriptions/v2ray_nodes.txt"
    assert subscription_snapshot["per_node"][0]["name"] == "lisahost"


def test_plan_and_apply_private_truth_sync_updates_repo_files(tmp_path: Path) -> None:
    runtime_workspace_root = tmp_path / "runtime-workspace"
    repo_root = tmp_path / "repo-root"

    runtime_inventory = runtime_workspace_root / "repos" / "proxy_ops_private" / "inventory"
    truth_inventory = repo_root / "repos" / "proxy_ops_private" / "inventory"
    runtime_inventory.mkdir(parents=True, exist_ok=True)
    truth_inventory.mkdir(parents=True, exist_ok=True)

    (runtime_inventory / "nodes.yaml").write_text("nodes:\n  - name: lisahost\n", encoding="utf-8")
    (runtime_inventory / "subscriptions.yaml").write_text("profile_name: runtime\n", encoding="utf-8")
    (truth_inventory / "nodes.yaml").write_text("nodes:\n  - name: stale\n", encoding="utf-8")
    (truth_inventory / "subscriptions.yaml").write_text("profile_name: stale\n", encoding="utf-8")

    plan = plan_private_truth_sync(runtime_workspace_root=runtime_workspace_root, repo_root=repo_root)

    assert len(plan.actions) == 2

    result = apply_private_truth_sync(plan=plan, confirm=True)

    assert result.updated_files == (
        "repos/proxy_ops_private/inventory/nodes.yaml",
        "repos/proxy_ops_private/inventory/subscriptions.yaml",
    )
    assert (truth_inventory / "nodes.yaml").read_text(encoding="utf-8") == "nodes:\n  - name: lisahost\n"
    assert (truth_inventory / "subscriptions.yaml").read_text(encoding="utf-8") == "profile_name: runtime\n"
    assert result.audit_path.exists()


def test_apply_private_truth_sync_rejects_target_drift(tmp_path: Path) -> None:
    runtime_workspace_root = tmp_path / "runtime-workspace"
    repo_root = tmp_path / "repo-root"

    runtime_inventory = runtime_workspace_root / "repos" / "proxy_ops_private" / "inventory"
    truth_inventory = repo_root / "repos" / "proxy_ops_private" / "inventory"
    runtime_inventory.mkdir(parents=True, exist_ok=True)
    truth_inventory.mkdir(parents=True, exist_ok=True)

    (runtime_inventory / "nodes.yaml").write_text("nodes:\n  - name: lisahost\n", encoding="utf-8")
    (runtime_inventory / "subscriptions.yaml").write_text("profile_name: runtime\n", encoding="utf-8")
    (truth_inventory / "nodes.yaml").write_text("nodes:\n  - name: stale\n", encoding="utf-8")
    (truth_inventory / "subscriptions.yaml").write_text("profile_name: stale\n", encoding="utf-8")

    plan = plan_private_truth_sync(runtime_workspace_root=runtime_workspace_root, repo_root=repo_root)
    (truth_inventory / "nodes.yaml").write_text("nodes:\n  - name: drifted\n", encoding="utf-8")

    with pytest.raises(ValueError, match="target file changed"):
        apply_private_truth_sync(plan=plan, confirm=True)


def test_load_public_host_console_rejects_non_boolean_should_publish(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "host_console.json"
    snapshot_path.write_text(
        """
{
  "generated_at": "2026-04-15T00:00:00Z",
  "hosts": [
    {
      "name": "lisahost",
      "provider": "Lisahost",
      "deployment_topology": "standalone_vps",
      "runtime_service": "cliproxy-plus",
      "observed_health": "healthy",
      "should_publish": "false",
      "publish_reason": "enabled_in_registry"
    }
  ]
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must define a boolean should_publish"):
        load_public_host_console(snapshot_path)
