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


def _write_remote_proxy_authority_surface(tmp_path: Path) -> None:
    remote_proxy_root = tmp_path / "repos" / "remote_proxy"
    (remote_proxy_root / "scripts").mkdir(parents=True, exist_ok=True)
    (remote_proxy_root / "config").mkdir(parents=True, exist_ok=True)
    (remote_proxy_root / "docs" / "deploy").mkdir(parents=True, exist_ok=True)
    (remote_proxy_root / "scripts" / "service.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (remote_proxy_root / "config" / "cliproxy-plus.env").write_text(
        "CLIPROXY_IMAGE=test\n"
        "CLIPROXY_PORT=10000\n"
        "CLIPROXY_MEMORY_LIMIT=512m\n"
        "CLIPROXY_MANAGEMENT_KEY=test-management\n"
        "CLIPROXY_MANAGEMENT_ALLOW_REMOTE=true\n"
        "CLIPROXY_API_KEY=test-api\n"
        "CLIPROXY_USAGE_STATISTICS_ENABLED=true\n",
        encoding="utf-8",
    )
    (remote_proxy_root / "docs" / "deploy" / "cliproxy-plus-standalone-vps.md").write_text(
        "# standalone runbook\n",
        encoding="utf-8",
    )
    (remote_proxy_root / "docs" / "deploy" / "infra-core-ubuntu-online.md").write_text(
        "# infra-core sidecar runbook\n",
        encoding="utf-8",
    )


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
    _write_remote_proxy_authority_surface(tmp_path)
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: operator
  supported_modes: [public, operator]
repos:
  - id: remote_proxy
    display_name: remote_proxy
    role: public_runtime_baseline
    required_modes: [operator]
    optional: false
    visibility: public
    default_url: https://example.com/remote_proxy.git
    default_path: repos/remote_proxy
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    observations_path: state/observed/hosts.json
    required_modes: [operator]
  jobs:
    audit_path: state/jobs/audit
    handoff_path: state/jobs/handoffs
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
        allow_apply: true
        executor: authority_handoff
      - id: decommission_host
        allow_apply: true
        executor: authority_handoff
authority_adapters:
  - id: remote_proxy_cliproxy_plus_standalone
    display_name: remote_proxy cliproxy-plus standalone handoff
    owner_repo_id: remote_proxy
    required_modes: [operator]
    job_kinds: [deploy_host]
    topology: standalone_vps
    runtime_service: cliproxy-plus
    handoff_method: service_script
    entrypoint: repos/remote_proxy/scripts/service.sh
    service_name: cliproxy-plus
    actions:
      deploy_host: install
    required_paths:
      - repos/remote_proxy
    required_env_files:
      - repos/remote_proxy/config/cliproxy-plus.env
    required_env_keys:
      - CLIPROXY_IMAGE
      - CLIPROXY_PORT
      - CLIPROXY_MEMORY_LIMIT
      - CLIPROXY_MANAGEMENT_KEY
      - CLIPROXY_MANAGEMENT_ALLOW_REMOTE
      - CLIPROXY_API_KEY
      - CLIPROXY_USAGE_STATISTICS_ENABLED
    rollback_owner: remote_proxy
    rollback_hint: Review remote_proxy install/update path before rollback.
    notes:
      - proxy-platform only creates a reviewed handoff artifact
  - id: remote_proxy_cliproxy_plus_standalone_decommission
    display_name: remote_proxy cliproxy-plus standalone decommission handoff
    owner_repo_id: remote_proxy
    required_modes: [operator]
    job_kinds: [decommission_host]
    topology: standalone_vps
    runtime_service: cliproxy-plus
    handoff_method: runbook_only
    entrypoint: repos/remote_proxy/docs/deploy/cliproxy-plus-standalone-vps.md
    actions:
      decommission_host: manual_service_removal
    required_paths:
      - repos/remote_proxy
    required_env_files:
      - repos/remote_proxy/config/cliproxy-plus.env
    required_env_keys:
      - CLIPROXY_MANAGEMENT_KEY
    rollback_owner: remote_proxy
    rollback_hint: Re-run reviewed install after remote cleanup if rollback is needed.
    notes:
      - remote_proxy does not expose a shared decommission command yet
  - id: remote_proxy_cliproxy_plus_infra_core_sidecar
    display_name: remote_proxy infra-core sidecar handoff
    owner_repo_id: remote_proxy
    required_modes: [operator]
    job_kinds: [deploy_host, decommission_host]
    topology: infra_core_sidecar
    runtime_service: cliproxy-plus
    handoff_method: runbook_only
    entrypoint: repos/remote_proxy/docs/deploy/infra-core-ubuntu-online.md
    actions:
      deploy_host: review_sidecar_deploy
      decommission_host: review_sidecar_decommission
    required_paths:
      - repos/remote_proxy
    downstream_required_paths:
      - /mnt/hdo/infra-core
    required_env_files: []
    required_env_keys: []
    rollback_owner: infra_core
    rollback_hint: Use infra-core compose rollback after owner review.
    notes:
      - do not run remote_proxy install.sh inside /mnt/hdo/infra-core
      - actual compose lifecycle remains owned by infra-core
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


def test_deploy_job_apply_creates_authority_handoff_artifact(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="deploy_host",
        requested_by="pytest",
        payload={"name": "lisahost"},
    )

    assert plan.apply_supported is True
    assert plan.executor == "authority_handoff"
    assert plan.authority_adapter_id == "remote_proxy_cliproxy_plus_standalone"
    assert plan.authority_topology == "standalone_vps"
    assert plan.handoff_action == "install"
    assert any("authority handoff artifact" in step.lower() for step in plan.preview_steps)

    result = apply_job_plan(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        plan=plan,
        requested_by="pytest",
        confirm=True,
    )

    assert result.status == "applied"
    assert result.executor == "authority_handoff"
    assert result.handoff_path is not None
    assert result.handoff_path.exists()
    handoff_payload = yaml.safe_load(result.handoff_path.read_text(encoding="utf-8"))
    assert handoff_payload["adapter"]["adapter_id"] == "remote_proxy_cliproxy_plus_standalone"
    assert handoff_payload["adapter"]["handoff_method"] == "service_script"
    assert handoff_payload["adapter"]["action"] == "install"
    assert handoff_payload["recommended_command"] == [
        "./scripts/service.sh",
        "cliproxy-plus",
        "install",
    ]

    audits = list_audit_records(manifest, tmp_path, "operator")
    assert audits[0].event == "applied"
    assert "authority handoff" in audits[0].summary


def test_decommission_job_apply_creates_runbook_only_authority_handoff_artifact(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="decommission_host",
        requested_by="pytest",
        payload={"name": "lisahost"},
    )

    assert plan.apply_supported is True
    assert plan.executor == "authority_handoff"
    assert plan.authority_adapter_id == "remote_proxy_cliproxy_plus_standalone_decommission"
    assert plan.handoff_action == "manual_service_removal"

    result = apply_job_plan(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        plan=plan,
        requested_by="pytest",
        confirm=True,
    )

    assert result.status == "applied"
    handoff_payload = yaml.safe_load(result.handoff_path.read_text(encoding="utf-8"))
    assert handoff_payload["adapter"]["adapter_id"] == "remote_proxy_cliproxy_plus_standalone_decommission"
    assert handoff_payload["adapter"]["handoff_method"] == "runbook_only"
    assert handoff_payload["adapter"]["action"] == "manual_service_removal"
    assert handoff_payload["recommended_command"] is None


def test_sidecar_authority_handoff_records_downstream_paths_without_local_mount(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    inventory_path = tmp_path / "operator" / "nodes.yaml"
    inventory_payload = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    inventory_payload["nodes"][0]["deployment_topology"] = "infra_core_sidecar"
    inventory_payload["nodes"][0]["runtime_service"] = "cliproxy-plus"
    inventory_path.write_text(yaml.safe_dump(inventory_payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    manifest = load_manifest(manifest_path)
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="deploy_host",
        requested_by="pytest",
        payload={"name": "lisahost"},
    )

    assert plan.authority_adapter_id == "remote_proxy_cliproxy_plus_infra_core_sidecar"
    assert any("record downstream execution paths" in step for step in plan.preview_steps)

    result = apply_job_plan(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        plan=plan,
        requested_by="pytest",
        confirm=True,
    )

    assert result.status == "applied"
    handoff_payload = yaml.safe_load(result.handoff_path.read_text(encoding="utf-8"))
    assert handoff_payload["required_paths"] == ["repos/remote_proxy"]
    assert handoff_payload["downstream_required_paths"] == ["/mnt/hdo/infra-core"]
    assert any("verify downstream execution paths exist" in step for step in handoff_payload["review_steps"])


def test_apply_rejects_authority_handoff_when_contract_changes_after_planning(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="deploy_host",
        requested_by="pytest",
        payload={"name": "lisahost"},
    )

    alternate_entrypoint = tmp_path / "repos" / "remote_proxy" / "scripts" / "service-alt.sh"
    alternate_entrypoint.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            "entrypoint: repos/remote_proxy/scripts/service.sh",
            "entrypoint: repos/remote_proxy/scripts/service-alt.sh",
        ),
        encoding="utf-8",
    )
    updated_manifest = load_manifest(manifest_path)

    with pytest.raises(JobPlanIntegrityError, match="authority handoff contract changed"):
        apply_job_plan(
            manifest=updated_manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=plan,
            requested_by="pytest",
            confirm=True,
        )



def test_apply_rejects_authority_handoff_when_required_files_are_missing(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="deploy_host",
        requested_by="pytest",
        payload={"name": "lisahost"},
    )

    (tmp_path / "repos" / "remote_proxy" / "config" / "cliproxy-plus.env").unlink()

    with pytest.raises(JobPlanIntegrityError, match="authority prerequisites missing"):
        apply_job_plan(
            manifest=manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=plan,
            requested_by="pytest",
            confirm=True,
        )



def test_apply_rejects_authority_handoff_when_required_env_key_is_missing(tmp_path: Path) -> None:
    manifest = load_manifest(_write_fixture(tmp_path))
    plan = plan_job(
        manifest=manifest,
        workspace_root=tmp_path,
        mode="operator",
        job_kind="deploy_host",
        requested_by="pytest",
        payload={"name": "lisahost"},
    )

    (tmp_path / "repos" / "remote_proxy" / "config" / "cliproxy-plus.env").write_text(
        "CLIPROXY_IMAGE=test\nCLIPROXY_MANAGEMENT_KEY=test-management\n",
        encoding="utf-8",
    )

    with pytest.raises(JobPlanIntegrityError, match="required env key"):
        apply_job_plan(
            manifest=manifest,
            workspace_root=tmp_path,
            mode="operator",
            plan=plan,
            requested_by="pytest",
            confirm=True,
        )



def test_plan_deploy_rejects_host_without_authority_classification(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    (tmp_path / "operator" / "nodes.yaml").write_text(
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
""",
        encoding="utf-8",
    )
    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match="missing deployment classification"):
        plan_job(
            manifest=manifest,
            workspace_root=tmp_path,
            mode="operator",
            job_kind="deploy_host",
            requested_by="pytest",
            payload={"name": "lisahost"},
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
