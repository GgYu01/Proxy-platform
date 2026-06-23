from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from proxy_platform.projections import build_host_views, build_subscription_projection
from proxy_platform.subscription_availability import (
    AvailabilityContext,
    AvailabilityPolicyView,
    evaluate_node_availability,
    is_subscription_eligible,
    load_availability_context,
)
from proxy_platform.inventory import load_host_registry
from proxy_platform.manifest import HostRegistrySource
from proxy_platform.state import load_host_registry as load_state_registry
from proxy_platform.state import load_host_observations
from proxy_platform.state import project_subscription


def _load_ops_availability_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "repos"
        / "proxy_ops_private"
        / "scripts"
        / "subscription_node_availability.py"
    )
    module_name = "subscription_node_availability_test_module"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _write_ops_fixture(tmp_path: Path, *, ledger: dict | None = None, exempt: bool = False) -> Path:
    repo_root = tmp_path / "proxy_ops_private"
    (repo_root / "inventory").mkdir(parents=True)
    (repo_root / "state").mkdir(parents=True)
    (repo_root / "inventory" / "nodes.yaml").write_text(
        f"""
nodes:
  - name: node_a
    host: 127.0.0.1
    ssh_port: 22
    base_port: 10000
    subscription_alias: Node A
    enabled: true
    include_in_subscription: true
    subscription_availability_exempt: {str(exempt).lower()}
    infra_core_candidate: false
    change_policy: mutable
    provider: test
  - name: node_b
    host: 127.0.0.2
    ssh_port: 22
    base_port: 10000
    subscription_alias: Node B
    enabled: true
    include_in_subscription: true
    infra_core_candidate: false
    change_policy: mutable
    provider: test
""",
        encoding="utf-8",
    )
    (repo_root / "inventory" / "subscriptions.yaml").write_text(
        """
profile_name: Test
subscription_base_url: https://example.com/subscriptions
remote_profile_name: Test Remote
update_interval_hours: 12
failover_priority: [node_a, node_b]
availability_policy:
  probe_port_offset: 3
  exclude_after_hours: 72
  min_published_nodes: 1
  probe_timeout_seconds: 0.1
  ledger_path: state/node_availability.json
""",
        encoding="utf-8",
    )
    payload = ledger or {"updated_at": "2026-06-07T00:00:00Z", "nodes": {}}
    (repo_root / "state" / "node_availability.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return repo_root


def test_subscription_eligible_excludes_node_after_72h(tmp_path: Path) -> None:
    module = _load_ops_availability_module()
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat().replace("+00:00", "Z")
    repo_root = _write_ops_fixture(
        tmp_path,
        ledger={
            "updated_at": "2026-06-07T00:00:00Z",
            "nodes": {
                "node_b": {
                    "last_probe_at": "2026-06-07T00:00:00Z",
                    "last_health": "down",
                    "unavailable_since": four_days_ago,
                    "last_success_at": "2026-05-01T00:00:00Z",
                    "detail": "tcp failed",
                }
            },
        },
    )

    eligible = module.subscription_eligible_nodes(repo_root)
    report = module.exclusion_report(repo_root)

    assert [node["name"] for node in eligible] == ["node_a"]
    assert report.excluded == ["node_b"]


def test_subscription_eligible_keeps_pending_node_before_72h(tmp_path: Path) -> None:
    module = _load_ops_availability_module()
    one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    repo_root = _write_ops_fixture(
        tmp_path,
        ledger={
            "updated_at": "2026-06-07T00:00:00Z",
            "nodes": {
                "node_b": {
                    "last_probe_at": "2026-06-07T00:00:00Z",
                    "last_health": "down",
                    "unavailable_since": one_day_ago,
                    "detail": "tcp failed",
                }
            },
        },
    )

    eligible = module.subscription_eligible_nodes(repo_root)
    report = module.exclusion_report(repo_root)

    assert [node["name"] for node in eligible] == ["node_a", "node_b"]
    assert report.pending == ["node_b"]


def test_ops_publishable_nodes_include_only_currently_healthy_nodes(tmp_path: Path) -> None:
    module = _load_ops_availability_module()
    repo_root = _write_ops_fixture(
        tmp_path,
        ledger={
            "updated_at": "2026-06-07T00:00:00Z",
            "nodes": {
                "node_a": {
                    "last_probe_at": "2026-06-07T00:00:00Z",
                    "last_health": "healthy",
                    "unavailable_since": None,
                    "last_success_at": "2026-06-07T00:00:00Z",
                    "detail": "tcp ok",
                },
                "node_b": {
                    "last_probe_at": "2026-06-07T00:00:00Z",
                    "last_health": "down",
                    "unavailable_since": "2026-06-06T00:00:00Z",
                    "detail": "tcp failed",
                },
            },
        },
    )

    publishable = module.subscription_publishable_nodes(repo_root)

    assert [node["name"] for node in publishable] == ["node_a"]


def test_ops_probe_policy_defaults_to_published_vless_port_offset(tmp_path: Path) -> None:
    module = _load_ops_availability_module()
    repo_root = _write_ops_fixture(tmp_path)

    policy = module.load_availability_policy(repo_root)

    assert policy.probe_port_offset == 3
    assert policy.probe_method == "mihomo_openai_http"
    assert policy.openai_probe_url == "https://api.openai.com/v1/models"
    assert 401 in policy.openai_expected_statuses


def test_probe_nodes_requires_real_proxy_success_even_when_tcp_connects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_ops_availability_module()
    repo_root = _write_ops_fixture(tmp_path)
    calls: list[tuple[str, int]] = []

    def fake_tcp_probe(*, host: str, port: int, timeout_seconds: float):
        calls.append((host, port))
        return True, f"tcp connect ok {host}:{port}"

    def fake_proxy_probe(*, repo_root: Path, node: dict, policy):
        return False, "openai proxy http failed status=000"

    monkeypatch.setattr(module, "_tcp_probe", fake_tcp_probe)
    monkeypatch.setattr(module, "_probe_node_through_mihomo", fake_proxy_probe)

    results = module.probe_nodes(repo_root)

    assert calls == [("127.0.0.1", 10003), ("127.0.0.2", 10003)]
    assert [result.health for result in results] == ["down", "down"]
    assert all("tcp=ok" in result.detail for result in results)
    assert all("proxy=failed" in result.detail for result in results)


def test_probe_nodes_marks_node_healthy_only_after_openai_http_proxy_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_ops_availability_module()
    repo_root = _write_ops_fixture(tmp_path)

    def fake_tcp_probe(*, host: str, port: int, timeout_seconds: float):
        return True, f"tcp connect ok {host}:{port}"

    def fake_proxy_probe(*, repo_root: Path, node: dict, policy):
        if node["name"] == "node_a":
            return True, "openai proxy http status=401"
        return False, "openai proxy http status=000"

    monkeypatch.setattr(module, "_tcp_probe", fake_tcp_probe)
    monkeypatch.setattr(module, "_probe_node_through_mihomo", fake_proxy_probe)

    ledger = module.update_ledger(repo_root, module.probe_nodes(repo_root))
    publishable = module.subscription_publishable_nodes(repo_root, ledger=ledger)

    assert ledger["nodes"]["node_a"]["last_health"] == "healthy"
    assert ledger["nodes"]["node_b"]["last_health"] == "down"
    assert [node["name"] for node in publishable] == ["node_a"]


def test_subscription_eligible_respects_exempt_flag(tmp_path: Path) -> None:
    module = _load_ops_availability_module()
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat().replace("+00:00", "Z")
    repo_root = _write_ops_fixture(
        tmp_path,
        exempt=True,
        ledger={
            "updated_at": "2026-06-07T00:00:00Z",
            "nodes": {
                "node_a": {
                    "last_probe_at": "2026-06-07T00:00:00Z",
                    "last_health": "down",
                    "unavailable_since": four_days_ago,
                    "detail": "tcp failed",
                }
            },
        },
    )

    eligible = module.subscription_eligible_nodes(repo_root)
    assert [node["name"] for node in eligible] == ["node_a", "node_b"]


def test_ensure_minimum_published_nodes_fail_fast(tmp_path: Path) -> None:
    module = _load_ops_availability_module()
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat().replace("+00:00", "Z")
    repo_root = _write_ops_fixture(
        tmp_path,
        ledger={
            "updated_at": "2026-06-07T00:00:00Z",
            "nodes": {
                "node_a": {
                    "unavailable_since": four_days_ago,
                    "last_health": "down",
                },
                "node_b": {
                    "unavailable_since": four_days_ago,
                    "last_health": "down",
                },
            },
        },
    )

    with pytest.raises(RuntimeError, match="subscription availability gate failed"):
        module.ensure_minimum_published_nodes(repo_root, module.subscription_publishable_nodes(repo_root))


def test_write_generated_artifacts_fails_fast_when_all_real_proxy_probes_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    render_path = (
        Path(__file__).resolve().parents[1]
        / "repos"
        / "proxy_ops_private"
        / "scripts"
        / "render_artifacts.py"
    )
    spec = importlib.util.spec_from_file_location("render_artifacts_fail_fast_test_module", render_path)
    assert spec is not None and spec.loader is not None
    render_artifacts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_artifacts)

    repo_root = _write_ops_fixture(
        tmp_path,
        ledger={
            "updated_at": "2026-06-23T00:00:00Z",
            "nodes": {
                "node_a": {
                    "last_health": "down",
                    "unavailable_since": "2026-06-23T00:00:00Z",
                    "detail": "tcp=ok; proxy=failed",
                },
                "node_b": {
                    "last_health": "down",
                    "unavailable_since": "2026-06-23T00:00:00Z",
                    "detail": "tcp=ok; proxy=failed",
                },
            },
        },
    )
    (repo_root / "secrets" / "nodes").mkdir(parents=True)
    for node_name in ("node_a", "node_b"):
        (repo_root / "secrets" / "nodes" / f"{node_name}.env").write_text(
            "\n".join(
                [
                    "VLESS_UUID=46e1f1cc-6476-4fbc-b25d-969fa643c816",
                    "REALITY_PUBLIC_KEY=public-key",
                    "REALITY_SHORT_ID=0123456789abcdef",
                    "REALITY_SERVER_NAMES=www.microsoft.com",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    monkeypatch.setenv("SKIP_AVAILABILITY_PROBE", "1")

    with pytest.raises(RuntimeError, match="eligible_nodes=0 < min_published_nodes=1"):
        render_artifacts.write_generated_artifacts(repo_root)


def test_platform_projection_excludes_unavailable_node(tmp_path: Path) -> None:
    operator_dir = tmp_path / "repos" / "proxy_ops_private" / "inventory"
    state_dir = tmp_path / "repos" / "proxy_ops_private" / "state"
    operator_dir.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat().replace("+00:00", "Z")
    (operator_dir / "nodes.yaml").write_text(
        """
nodes:
  - name: lisahost
    host: 1.2.3.4
    ssh_port: 22
    base_port: 10000
    subscription_alias: Lisa
    enabled: true
    include_in_subscription: true
    infra_core_candidate: false
    change_policy: frozen
    provider: Lisahost
  - name: vmrack1
    host: 5.6.7.8
    ssh_port: 22
    base_port: 10000
    subscription_alias: VM1
    enabled: true
    include_in_subscription: true
    infra_core_candidate: false
    change_policy: mutable
    provider: vmrack
""",
        encoding="utf-8",
    )
    (operator_dir / "subscriptions.yaml").write_text(
        """
profile_name: GG Proxy Nodes
subscription_base_url: https://example.com/subscriptions
remote_profile_name: GG Proxy Nodes Remote
update_interval_hours: 12
failover_priority: [lisahost, vmrack1]
availability_policy:
  exclude_after_hours: 72
  ledger_path: state/node_availability.json
""",
        encoding="utf-8",
    )
    (state_dir / "node_availability.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-06-07T00:00:00Z",
                "nodes": {
                    "vmrack1": {
                        "last_health": "down",
                        "unavailable_since": four_days_ago,
                        "detail": "tcp failed",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    source = HostRegistrySource(
        inventory_path=Path("repos/proxy_ops_private/inventory/nodes.yaml"),
        subscriptions_path=Path("repos/proxy_ops_private/inventory/subscriptions.yaml"),
        observations_path=None,
    )
    registry = load_host_registry(source, tmp_path)
    context = load_availability_context(tmp_path)

    projection = build_subscription_projection(registry, availability_context=context)
    views = {view.name: view for view in build_host_views(registry, availability_context=context)}

    assert [item.name for item in projection.per_node] == ["lisahost"]
    assert projection.excluded_availability[0].name == "vmrack1"
    assert views["vmrack1"].should_publish is False
    assert views["vmrack1"].publish_reason == "auto_excluded_unavailable_72h"
    assert views["lisahost"].should_publish is True


def test_state_project_subscription_pending_vs_excluded(tmp_path: Path) -> None:
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat().replace("+00:00", "Z")
    one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
hosts:
  - host_id: pending-host
    display_name: Pending
    endpoint: https://pending.example.com/sub
    provider: cliproxy_plus
    enabled: true
    include_in_subscription: true
  - host_id: excluded-host
    display_name: Excluded
    endpoint: https://excluded.example.com/sub
    provider: cliproxy_plus
    enabled: true
    include_in_subscription: true
""",
        encoding="utf-8",
    )
    context = AvailabilityContext(
        policy=AvailabilityPolicyView(exclude_after_hours=72, ledger_path=tmp_path / "ledger.json"),
        ledger_nodes={
            "pending-host": {"unavailable_since": one_day_ago},
            "excluded-host": {"unavailable_since": four_days_ago},
        },
    )

    projection = project_subscription(load_state_registry(registry_path), availability_context=context)

    assert [member.host_id for member in projection.members] == ["pending-host"]
    assert projection.members[0].reason.startswith("included: pending availability")
    assert "excluded-host" in projection.excluded_host_ids


def test_is_subscription_eligible_unknown_ledger_keeps_node() -> None:
    assert is_subscription_eligible(
        node_name="node_a",
        subscription_availability_exempt=False,
        context=AvailabilityContext(policy=None, ledger_nodes={}),
    )
