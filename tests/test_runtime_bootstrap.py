from pathlib import Path

import pytest

from proxy_platform.runtime_bootstrap import RuntimeBootstrapError
from proxy_platform.runtime_bootstrap import bootstrap_runtime_workspace


def _write_runtime_seed(seed_root: Path) -> None:
    (seed_root / "operator").mkdir(parents=True, exist_ok=True)
    (seed_root / "state" / "observations").mkdir(parents=True, exist_ok=True)
    (seed_root / "authority" / "remote_proxy" / "scripts").mkdir(parents=True, exist_ok=True)
    (seed_root / "authority" / "remote_proxy" / "config").mkdir(parents=True, exist_ok=True)
    (seed_root / "authority" / "remote_proxy" / "docs" / "deploy").mkdir(parents=True, exist_ok=True)

    (seed_root / "operator" / "nodes.yaml").write_text(
        "nodes:\n  - name: lisahost\n    host: 38.34.8.59\n    ssh_port: 27823\n"
        "    base_port: 10000\n    subscription_alias: GG-Lisa-Stable\n    enabled: true\n"
        "    include_in_subscription: true\n    infra_core_candidate: true\n"
        "    change_policy: frozen\n    provider: Lisahost\n"
        "    deployment_topology: standalone_vps\n    runtime_service: cliproxy-plus\n",
        encoding="utf-8",
    )
    (seed_root / "operator" / "subscriptions.yaml").write_text(
        "profile_name: GG Proxy Nodes\nsubscription_base_url: https://example.com/subscriptions\n"
        "hiddify_fragment_name: GG Proxy Nodes\nremote_profile_name: GG Proxy Nodes Remote\n"
        "update_interval_hours: 12\n",
        encoding="utf-8",
    )
    (seed_root / "state" / "observations" / "hosts.json").write_text(
        "{\n  \"hosts\": []\n}\n",
        encoding="utf-8",
    )
    (seed_root / "authority" / "remote_proxy" / "scripts" / "service.sh").write_text(
        "#!/bin/sh\nexit 0\n",
        encoding="utf-8",
    )
    (seed_root / "authority" / "remote_proxy" / "config" / "cliproxy-plus.env").write_text(
        "CLIPROXY_IMAGE=test\nCLIPROXY_PORT=10000\nCLIPROXY_MEMORY_LIMIT=512m\n"
        "CLIPROXY_MANAGEMENT_KEY=demo\nCLIPROXY_MANAGEMENT_ALLOW_REMOTE=true\n"
        "CLIPROXY_API_KEY=demo\nCLIPROXY_USAGE_STATISTICS_ENABLED=true\n",
        encoding="utf-8",
    )
    (seed_root / "authority" / "remote_proxy" / "docs" / "deploy" / "cliproxy-plus-standalone-vps.md").write_text(
        "# standalone\n",
        encoding="utf-8",
    )
    (seed_root / "authority" / "remote_proxy" / "docs" / "deploy" / "infra-core-ubuntu-online.md").write_text(
        "# infra core\n",
        encoding="utf-8",
    )


def test_bootstrap_runtime_workspace_seeds_minimal_operator_surface(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    workspace_root = tmp_path / "workspace"
    _write_runtime_seed(seed_root)

    result = bootstrap_runtime_workspace(seed_root=seed_root, workspace_root=workspace_root)

    assert (
        workspace_root / "repos" / "proxy_ops_private" / "inventory" / "nodes.yaml"
    ).read_text(encoding="utf-8").startswith("nodes:")
    assert (workspace_root / "repos" / "remote_proxy" / "scripts" / "service.sh").exists()
    assert (workspace_root / "state" / "jobs" / "audit").is_dir()
    assert (workspace_root / "state" / "jobs" / "handoffs").is_dir()
    assert any("proxy_ops_private/inventory/nodes.yaml" in item for item in result.seeded_files)


def test_bootstrap_runtime_workspace_preserves_existing_runtime_truth(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    workspace_root = tmp_path / "workspace"
    _write_runtime_seed(seed_root)

    existing_nodes = workspace_root / "repos" / "proxy_ops_private" / "inventory" / "nodes.yaml"
    existing_nodes.parent.mkdir(parents=True, exist_ok=True)
    existing_nodes.write_text("nodes:\n  - name: existing\n", encoding="utf-8")

    result = bootstrap_runtime_workspace(seed_root=seed_root, workspace_root=workspace_root)

    assert existing_nodes.read_text(encoding="utf-8") == "nodes:\n  - name: existing\n"
    assert any("proxy_ops_private/inventory/nodes.yaml" in item for item in result.preserved_files)


def test_bootstrap_runtime_workspace_refreshes_authority_review_surface(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    workspace_root = tmp_path / "workspace"
    _write_runtime_seed(seed_root)

    existing_service_script = workspace_root / "repos" / "remote_proxy" / "scripts" / "service.sh"
    existing_service_script.parent.mkdir(parents=True, exist_ok=True)
    existing_service_script.write_text("#!/bin/sh\necho stale\n", encoding="utf-8")

    result = bootstrap_runtime_workspace(seed_root=seed_root, workspace_root=workspace_root)

    assert existing_service_script.read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n"
    assert any("repos/remote_proxy/scripts/service.sh" in item for item in result.refreshed_files)


def test_bootstrap_runtime_workspace_requires_required_seed_files(tmp_path: Path) -> None:
    seed_root = tmp_path / "seed"
    seed_root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(RuntimeBootstrapError, match="missing required runtime seed file"):
        bootstrap_runtime_workspace(seed_root=seed_root, workspace_root=tmp_path / "workspace")
