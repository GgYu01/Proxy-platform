from pathlib import Path
import json

import pytest
import yaml

import proxy_platform.jobs as jobs_module
from proxy_platform.inventory import load_host_registry as load_operator_registry
from proxy_platform.jobs import apply_job_plan
from proxy_platform.jobs import JobApplyUnsupportedError
from proxy_platform.jobs import JobPlanIntegrityError
from proxy_platform.jobs import list_audit_records
from proxy_platform.jobs import load_job_plan
from proxy_platform.jobs import plan_job
from proxy_platform.manifest import load_manifest
from proxy_platform.projections import build_subscription_projection


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
  default_mode: operator
  supported_modes: [public, operator]
repos: []
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    observations_path: state/observed/hosts.json
    required_modes: [operator]
  jobs:
    audit_path: state/jobs/audit
    required_modes: [operator]
    require_confirmation: true
    kinds:
      - id: add_host
        allow_apply: true
        executor: inventory_only
      - id: remove_host
        allow_apply: true
        executor: inventory_only
      - id: deploy_host
        allow_apply: false
        executor: not_configured
      - id: decommission_host
        allow_apply: false
        executor: not_configured
commands: {}
""",
        encoding="utf-8",
    )
    return manifest_path


def test_plan_add_host_writes_job_plan_and_audit_record(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))

    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
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

    assert plan.job_kind == "add_host"
    assert plan.apply_supported is True
    assert plan.requires_confirmation is True
    assert any("inventory" in step.lower() for step in plan.preview_steps)
    assert plan.plan_path.exists()
    reloaded = load_job_plan(plan.plan_path)
    assert reloaded.job_id == plan.job_id
    assert reloaded.plan_digest == plan.plan_digest

    audits = list_audit_records(manifest, tmp_path, "operator")
    assert audits[0].job_id == plan.job_id
    assert audits[0].event == "planned"
    assert audits[0].plan_digest == plan.plan_digest


def test_apply_add_host_job_updates_inventory_and_records_apply_audit(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
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

    result = apply_job_plan(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        plan=plan,
        requested_by="pytest",
        confirm=True,
    )

    assert result.status == "applied"
    inventory_payload = yaml.safe_load((tmp_path / "operator" / "nodes.yaml").read_text(encoding="utf-8"))
    assert any(item["name"] == "vmrack1" for item in inventory_payload["nodes"])

    audits = list_audit_records(manifest, tmp_path, "operator")
    assert [record.event for record in audits[:2]] == ["applied", "planned"]


def test_apply_add_host_job_supports_include_in_subscription_flag(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
            "name": "vmrack1",
            "host": "38.65.93.39",
            "ssh_port": 22,
            "base_port": 10000,
            "subscription_alias": "GG-Vmrack1",
            "enabled": True,
            "include_in_subscription": False,
            "infra_core_candidate": True,
            "change_policy": "mutable",
            "provider": "vmrack",
        },
    )

    result = apply_job_plan(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        plan=plan,
        requested_by="pytest",
        confirm=True,
    )

    assert result.status == "applied"
    registry = load_operator_registry(manifest.host_registry, tmp_path)
    added = next(node for node in registry.nodes if node.name == "vmrack1")
    assert added.include_in_subscription is False

    projection = build_subscription_projection(registry)
    assert all(node.name != "vmrack1" for node in projection.per_node)


def test_apply_job_requires_confirmation_when_policy_demands_it(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="remove_host",
        requested_by="pytest",
        payload={"name": "lisahost"},
    )

    with pytest.raises(ValueError):
        apply_job_plan(
            manifest=manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=plan,
            requested_by="pytest",
            confirm=False,
        )


def test_deploy_job_is_dry_run_only_until_executor_is_configured(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="deploy_host",
        requested_by="pytest",
        payload={"name": "lisahost"},
    )

    assert plan.apply_supported is False
    assert plan.executor == "not_configured"
    assert any("remote_proxy" in step for step in plan.preview_steps)

    with pytest.raises(JobApplyUnsupportedError):
        apply_job_plan(
            manifest=manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=plan,
            requested_by="pytest",
            confirm=True,
        )


def test_apply_rejects_tampered_plan_file(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
            "name": "reviewed-host",
            "host": "38.65.93.39",
            "ssh_port": 22,
            "base_port": 10000,
            "subscription_alias": "GG-Reviewed",
            "enabled": True,
            "infra_core_candidate": True,
            "change_policy": "mutable",
            "provider": "vmrack",
        },
    )

    stored_plan = json.loads(plan.plan_path.read_text(encoding="utf-8"))
    stored_plan["payload"]["name"] = "tampered-host"
    plan.plan_path.write_text(json.dumps(stored_plan, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(JobPlanIntegrityError):
        apply_job_plan(
            manifest=manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=load_job_plan(plan.plan_path),
            requested_by="pytest",
            confirm=True,
        )


def test_plan_output_must_stay_inside_managed_plan_directory(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))

    with pytest.raises(JobPlanIntegrityError):
        plan_job(
            manifest=manifest,
            workspace_root=tmp_path,
            mode="operator",
            job_kind="add_host",
            requested_by="pytest",
            payload={
                "name": "vmrack2",
                "host": "38.65.93.94",
                "ssh_port": 22,
                "base_port": 10000,
                "subscription_alias": "GG-Vmrack2",
                "enabled": True,
                "infra_core_candidate": True,
                "change_policy": "mutable",
                "provider": "vmrack",
            },
            output_path=tmp_path / "outside-plan.json",
        )


def test_job_ids_stay_unique_even_with_fixed_timestamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    fixed_now = jobs_module.datetime(2026, 4, 14, 12, 0, 0, tzinfo=jobs_module.timezone.utc)
    monkeypatch.setattr(jobs_module, "_now", lambda: fixed_now)

    first = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
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
    second = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
            "name": "vmrack2",
            "host": "38.65.93.94",
            "ssh_port": 22,
            "base_port": 10000,
            "subscription_alias": "GG-Vmrack2",
            "enabled": True,
            "infra_core_candidate": True,
            "change_policy": "mutable",
            "provider": "vmrack",
        },
    )

    assert first.job_id != second.job_id
    assert first.plan_path != second.plan_path


def test_apply_rechecks_current_manifest_policy_before_executing(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
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

    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: operator
  supported_modes: [public, operator]
repos: []
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    observations_path: state/observed/hosts.json
    required_modes: [operator]
  jobs:
    audit_path: state/jobs/audit
    required_modes: [operator]
    require_confirmation: true
    kinds:
      - id: add_host
        allow_apply: false
        executor: inventory_only
      - id: remove_host
        allow_apply: true
        executor: inventory_only
      - id: deploy_host
        allow_apply: false
        executor: not_configured
      - id: decommission_host
        allow_apply: false
        executor: not_configured
commands: {}
""",
        encoding="utf-8",
    )
    updated_manifest = load_manifest(manifest_path)

    with pytest.raises(JobApplyUnsupportedError):
        apply_job_plan(
            manifest=updated_manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=plan,
            requested_by="pytest",
            confirm=True,
        )


def test_apply_rejects_plan_when_executor_contract_changed_after_planning(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
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

    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: operator
  supported_modes: [public, operator]
repos: []
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    observations_path: state/observed/hosts.json
    required_modes: [operator]
  jobs:
    audit_path: state/jobs/audit
    required_modes: [operator]
    require_confirmation: true
    kinds:
      - id: add_host
        allow_apply: true
        executor: authority_adapter
      - id: remove_host
        allow_apply: true
        executor: inventory_only
      - id: deploy_host
        allow_apply: false
        executor: not_configured
      - id: decommission_host
        allow_apply: false
        executor: not_configured
commands: {}
""",
        encoding="utf-8",
    )
    updated_manifest = load_manifest(manifest_path)

    with pytest.raises(JobPlanIntegrityError):
        apply_job_plan(
            manifest=updated_manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=plan,
            requested_by="pytest",
            confirm=True,
        )


def test_apply_rejects_replayed_plan_even_if_plan_file_status_is_reverted(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="add_host",
        requested_by="pytest",
        payload={
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

    apply_job_plan(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        plan=plan,
        requested_by="pytest",
        confirm=True,
    )

    stored_plan = json.loads(plan.plan_path.read_text(encoding="utf-8"))
    stored_plan["status"] = "planned"
    plan.plan_path.write_text(json.dumps(stored_plan, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(JobPlanIntegrityError):
        apply_job_plan(
            manifest=manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=load_job_plan(plan.plan_path),
            requested_by="pytest",
            confirm=True,
        )
