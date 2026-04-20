import base64
from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from proxy_platform.web_app import create_app


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
  default_mode: public
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
  local_providers:
    - id: local_mcp_pool
      display_name: Local MCP pool
      kind: mcp
      startup_timeout_seconds: 15
      request_timeout_seconds: 45
      startup_max_attempts: 3
      request_max_attempts: 2
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

    overview_response = client.get("/")
    hosts_page = client.get("/hosts")
    subscriptions_page = client.get("/subscriptions")
    providers_page = client.get("/providers")
    jobs_page = client.get("/jobs")
    audit_page = client.get("/audit")

    assert overview_response.status_code == 200
    assert hosts_page.status_code == 200
    assert subscriptions_page.status_code == 200
    assert providers_page.status_code == 200
    assert jobs_page.status_code == 200
    assert audit_page.status_code == 200

    assert 'class="console-shell"' in overview_response.text
    assert 'href="/hosts"' in overview_response.text
    assert 'href="/subscriptions"' in overview_response.text
    assert 'href="/providers"' in overview_response.text
    assert 'href="/jobs"' in overview_response.text
    assert 'href="/audit"' in overview_response.text
    assert "现场摘要" in overview_response.text
    assert "处理入口" in overview_response.text
    assert "摘要与分流" in overview_response.text
    assert "主机现场" in overview_response.text
    assert "链接与入口" in overview_response.text
    assert "本地预算" in overview_response.text
    assert "计划与确认" in overview_response.text
    assert "结果回看" in overview_response.text
    assert "这页先负责什么" not in overview_response.text
    assert "它不直接做什么" not in overview_response.text
    assert "处理顺序建议" not in overview_response.text
    assert 'class="overview-shell"' in overview_response.text
    assert 'class="overview-main-column"' in overview_response.text
    assert 'class="overview-side-column"' in overview_response.text
    assert 'class="panel panel-primary-summary"' in overview_response.text
    assert 'class="panel panel-workspace-rail"' in overview_response.text
    assert "summary-card-featured" in overview_response.text
    assert "host-preview-item" in overview_response.text
    assert 'id="recent-plan-card"' not in overview_response.text
    assert 'id="add-host-form"' not in overview_response.text
    assert '/static/operator_console.css' in overview_response.text
    assert '/static/operator_console.js' in overview_response.text

    assert "主机现场清单" in hosts_page.text
    assert "lisahost" in hosts_page.text
    assert 'id="host-search"' in hosts_page.text
    assert 'id="add-host-form"' not in hosts_page.text

    assert "订阅入口" in subscriptions_page.text
    assert "https://example.com/subscriptions/v2ray_nodes.txt" in subscriptions_page.text
    assert "手动订阅 URL" in subscriptions_page.text
    assert "Hiddify Deep Link" in subscriptions_page.text
    assert "不要粘贴到手动订阅 URL" in subscriptions_page.text
    assert "打开 Hiddify" in subscriptions_page.text
    assert "复制 Hiddify Deep Link" in subscriptions_page.text
    assert 'id="add-host-form"' not in subscriptions_page.text

    assert "本地 provider 生命周期" in providers_page.text
    assert "local_mcp_pool" in providers_page.text

    assert "主机登记作业" in jobs_page.text
    assert 'id="add-host-form"' in jobs_page.text
    assert 'id="remove-host-form"' in jobs_page.text
    assert 'id="remote-plan-form"' in jobs_page.text
    assert 'id="apply-plan-form"' in jobs_page.text
    assert "最近计划" in jobs_page.text

    assert "作业审计" in audit_page.text
    assert 'id="audit-list"' in audit_page.text
    assert "window.location.reload()" not in audit_page.text


def test_web_app_surfaces_worker_quotas_when_control_plane_read_client_is_configured(
    tmp_path: Path,
) -> None:
    manifest_path = _write_fixture(tmp_path)

    class FakeControlPlaneReadClient:
        def fetch_worker_quotas(self):
            return {
                "meta": {
                    "captured_at": "2026-04-20T01:49:10Z",
                    "worker_total": 2,
                    "worker_realtime": 1,
                    "worker_fallback": 0,
                    "worker_failed": 1,
                    "account_total": 3,
                    "accounts_with_snapshot": 2,
                    "accounts_without_snapshot": 1,
                    "fresh_probe_failures": 1,
                },
                "workers": [
                    {
                        "worker_id": "vmrack1_codex_primary",
                        "status": "failed",
                        "captured_at": "2026-04-20T01:49:10Z",
                        "group_ids": ["codex_group_a"],
                        "account_total": 1,
                        "accounts_with_snapshot": 0,
                        "accounts_without_snapshot": 1,
                        "fresh_probe_failures": 1,
                        "accounts": [
                            {
                                "account_id": "codex_group_a:fbdfb813bfca32bd",
                                "group_id": "codex_group_a",
                                "provider": "codex",
                                "auth_name": "codex-62843a39-DestineeConnellypaor@outlook.com-team.json",
                                "email": "DestineeConnellypaor@outlook.com",
                                "account_status": "active",
                                "probe_status": "error",
                                "probe_message": "Latest refresh failed on the worker.",
                                "probe_observed_at": "2026-04-20T01:46:43Z",
                                "latest_snapshot_present": False,
                                "quota_summary": "无最新配额快照",
                                "reset_at": None,
                                "capability_level": "unavailable",
                                "source_endpoint": None,
                            }
                        ],
                    },
                    {
                        "worker_id": "lisahost_codex_primary",
                        "status": "realtime",
                        "captured_at": "2026-04-20T01:49:10Z",
                        "group_ids": ["codex_group_lisahost"],
                        "account_total": 2,
                        "accounts_with_snapshot": 2,
                        "accounts_without_snapshot": 0,
                        "fresh_probe_failures": 0,
                        "accounts": [
                            {
                                "account_id": "codex_group_lisahost:4d4b8a7bead017fb",
                                "group_id": "codex_group_lisahost",
                                "provider": "codex",
                                "auth_name": "codex-xxx61421@gmail.com-pro.json",
                                "email": "xxx61421@gmail.com",
                                "account_status": "active",
                                "probe_status": "ok",
                                "probe_message": "Latest refresh succeeded.",
                                "probe_observed_at": "2026-04-20T01:48:07Z",
                                "latest_snapshot_present": True,
                                "quota_summary": "P93% / S33%",
                                "reset_at": "2026-04-20T05:24:13Z",
                                "capability_level": "authoritative_quota",
                                "source_endpoint": "/v0/management/api-call -> https://chatgpt.com/backend-api/wham/usage",
                            },
                            {
                                "account_id": "codex_group_lisahost:extra",
                                "group_id": "codex_group_lisahost",
                                "provider": "codex",
                                "auth_name": "codex-backup-oauth.json",
                                "email": "backup@example.com",
                                "account_status": "active",
                                "probe_status": "ok",
                                "probe_message": "Latest refresh succeeded.",
                                "probe_observed_at": "2026-04-20T01:48:08Z",
                                "latest_snapshot_present": True,
                                "quota_summary": "P100% / S100%",
                                "reset_at": "2026-04-20T06:48:00Z",
                                "capability_level": "authoritative_quota",
                                "source_endpoint": "/v0/management/api-call -> https://chatgpt.com/backend-api/wham/usage",
                            },
                        ],
                    },
                ],
            }

    client = TestClient(
        create_app(
            manifest_path,
            tmp_path,
            mode="operator",
            control_plane_read_client=FakeControlPlaneReadClient(),
        )
    )

    overview_response = client.get("/")
    worker_quotas_response = client.get("/worker-quotas")
    api_response = client.get("/api/worker-quotas")

    assert overview_response.status_code == 200
    assert worker_quotas_response.status_code == 200
    assert api_response.status_code == 200

    assert 'href="/worker-quotas"' in overview_response.text
    assert "远端 worker 配额" in overview_response.text
    assert "oauth 文件配额" in worker_quotas_response.text
    assert "vmrack1_codex_primary" in worker_quotas_response.text
    assert "lisahost_codex_primary" in worker_quotas_response.text
    assert "codex-xxx61421@gmail.com-pro.json" in worker_quotas_response.text
    assert "P93% / S33%" in worker_quotas_response.text
    assert "无最新配额快照" in worker_quotas_response.text

    payload = api_response.json()
    assert payload["meta"]["worker_total"] == 2
    assert payload["meta"]["accounts_with_snapshot"] == 2
    assert payload["workers"][0]["worker_id"] == "vmrack1_codex_primary"


def test_web_app_hides_worker_quota_view_when_control_plane_read_client_is_not_configured(
    tmp_path: Path,
) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    overview_response = client.get("/")
    page_response = client.get("/worker-quotas")
    api_response = client.get("/api/worker-quotas")

    assert overview_response.status_code == 200
    assert 'href="/worker-quotas"' not in overview_response.text
    assert page_response.status_code == 404
    assert page_response.json()["detail"] == "worker quota view is not configured"
    assert api_response.status_code == 404
    assert api_response.json()["detail"] == "worker quota view is not configured"


def test_web_app_returns_bad_gateway_when_control_plane_read_client_fails(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)

    class FailingControlPlaneReadClient:
        def fetch_worker_quotas(self):
            raise RuntimeError("upstream read failed")

    client = TestClient(
        create_app(
            manifest_path,
            tmp_path,
            mode="operator",
            control_plane_read_client=FailingControlPlaneReadClient(),
        )
    )

    response = client.get("/api/worker-quotas")

    assert response.status_code == 502
    assert response.json()["detail"] == "upstream read failed"


def test_web_app_requires_basic_auth_when_credentials_are_configured(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(
        create_app(
            manifest_path,
            tmp_path,
            mode="operator",
            basic_auth_username="operator",
            basic_auth_password="secret-pass",
        )
    )

    unauthorized = client.get("/api/hosts")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == 'Basic realm="proxy-platform"'

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    token = base64.b64encode(b"operator:secret-pass").decode("ascii")
    authorized = client.get("/api/hosts", headers={"Authorization": f"Basic {token}"})
    assert authorized.status_code == 200
    assert authorized.json()["hosts"][0]["name"] == "lisahost"


def test_web_app_can_plan_and_apply_host_mutation_jobs(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    add_plan_response = client.post(
        "/api/jobs/plan",
        json={
            "job_kind": "add_host",
            "payload": {
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
        },
    )
    assert add_plan_response.status_code == 200
    assert add_plan_response.json()["plan"]["job_kind"] == "add_host"
    assert add_plan_response.json()["plan"]["apply_supported"] is True

    apply_response = client.post(
        "/api/jobs/apply",
        json={"plan_path": add_plan_response.json()["plan"]["plan_path"], "confirm": True},
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["result"]["status"] == "applied"

    delete_plan_response = client.post(
        "/api/jobs/plan",
        json={"job_kind": "remove_host", "payload": {"name": "vmrack1"}},
    )
    assert delete_plan_response.status_code == 200
    assert delete_plan_response.json()["plan"]["job_kind"] == "remove_host"

    delete_apply_response = client.post(
        "/api/jobs/apply",
        json={"plan_path": delete_plan_response.json()["plan"]["plan_path"], "confirm": True},
    )
    assert delete_apply_response.status_code == 200
    assert delete_apply_response.json()["result"]["status"] == "applied"

    jobs_response = client.get("/api/jobs")
    assert jobs_response.status_code == 200
    assert len(jobs_response.json()["jobs"]) >= 4


def test_web_app_supports_public_mode_with_sanitized_snapshots(tmp_path: Path) -> None:
    public_dir = tmp_path / "state" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "host_console.json").write_text(
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
      "should_publish": true,
      "publish_reason": "enabled_in_registry"
    }
  ]
}
""",
        encoding="utf-8",
    )
    (public_dir / "subscriptions.json").write_text(
        """
{
  "generated_at": "2026-04-15T00:00:00Z",
  "profile_name": "GG Proxy Nodes",
  "multi_node_url": "https://example.com/subscriptions/v2ray_nodes.txt",
  "multi_node_hiddify_import": "hiddify://import/test#GG",
  "remote_profile_url": "https://example.com/subscriptions/singbox-client-profile.json",
  "per_node": [
    {
      "name": "lisahost",
      "alias": "GG-Lisa-Stable",
      "observed_health": "healthy",
      "v2ray_url": "https://example.com/subscriptions/v2ray_node_lisahost.txt",
      "hiddify_import_url": "hiddify://import/test#GG-Lisa-Stable"
    }
  ]
}
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
  supported_modes: [public]
repos: []
state_sources:
  - id: public_host_console_snapshot
    display_name: Public Host Console Snapshot
    description: sanitized public host console
    kind: public_host_console_snapshot
    repo_id: proxy-platform
    path: state/public/host_console.json
    ownership: public_projection
    required_modes: [public]
  - id: public_subscription_snapshot
    display_name: Public Subscription Snapshot
    description: sanitized public subscriptions
    kind: public_subscription_snapshot
    repo_id: proxy-platform
    path: state/public/subscriptions.json
    ownership: public_projection
    required_modes: [public]
projections:
  - id: public_host_console
    display_name: Public Host Console
    description: public host view
    kind: public_host_console_projection
    source_ids: [public_host_console_snapshot]
    required_modes: [public]
    rules: {}
  - id: public_subscription_nodes
    display_name: Public Subscription View
    description: public subscription view
    kind: public_subscription_projection
    source_ids: [public_subscription_snapshot]
    required_modes: [public]
    rules: {}
commands: {}
""",
        encoding="utf-8",
    )

    client = TestClient(create_app(manifest_path, tmp_path, mode="public"))

    hosts_response = client.get("/api/hosts")
    assert hosts_response.status_code == 200
    assert hosts_response.json()["hosts"][0]["name"] == "lisahost"
    assert "host" not in hosts_response.json()["hosts"][0]

    subscriptions_response = client.get("/api/subscriptions")
    assert subscriptions_response.status_code == 200
    assert subscriptions_response.json()["multi_node_url"] == "https://example.com/subscriptions/v2ray_nodes.txt"

    overview_response = client.get("/")
    hosts_page = client.get("/hosts")
    subscriptions_page = client.get("/subscriptions")
    providers_page = client.get("/providers")
    jobs_page = client.get("/jobs")
    audit_page = client.get("/audit")

    assert overview_response.status_code == 200
    assert hosts_page.status_code == 200
    assert subscriptions_page.status_code == 200
    assert providers_page.status_code == 200
    assert jobs_page.status_code == 404
    assert audit_page.status_code == 404

    assert "当前是只读视角" in overview_response.text
    assert 'class="console-shell"' in overview_response.text
    assert '/static/operator_console.css' in overview_response.text
    assert 'href="/jobs"' not in overview_response.text
    assert 'href="/audit"' not in overview_response.text

    assert "主机现场清单" in hosts_page.text
    assert "lisahost" in hosts_page.text
    assert "change_policy:" not in hosts_page.text

    assert "订阅入口" in subscriptions_page.text
    assert "手动订阅 URL" in subscriptions_page.text
    assert "GG-Lisa-Stable" in subscriptions_page.text

    assert "本地 provider 生命周期" in providers_page.text


def test_web_app_serves_console_static_assets(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    css_response = client.get("/static/operator_console.css")
    js_response = client.get("/static/operator_console.js")

    assert css_response.status_code == 200
    assert ".console-shell" in css_response.text
    assert js_response.status_code == 200
    assert "showToast" in js_response.text
    assert "function auditTone" in js_response.text
    assert "refreshObservations" in js_response.text


def test_web_app_bootstraps_missing_observations_before_loading_state(monkeypatch, tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    observations_path = tmp_path / "state" / "observed" / "hosts.json"
    observations_path.unlink()

    def fake_refresh(**kwargs):
        observations_path.parent.mkdir(parents=True, exist_ok=True)
        observations_path.write_text(
            """
{
  "generated_at": "2026-04-15T08:00:00Z",
  "hosts": [
    {
      "name": "lisahost",
      "health": "healthy",
      "source": "tcp_probe",
      "observed_at": "2026-04-15T08:00:00Z",
      "detail": "tcp connect ok 38.34.8.59:10001"
    }
  ]
}
""",
            encoding="utf-8",
        )
        return None

    monkeypatch.setattr("proxy_platform.web_app.refresh_host_observations", fake_refresh)

    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))
    response = client.get("/api/hosts")

    assert response.status_code == 200
    assert response.json()["hosts"][0]["observed_health"] == "healthy"


def test_web_app_can_force_refresh_observations(monkeypatch, tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    def fake_refresh(**kwargs):
        return {
            "observations_path": str(tmp_path / "state" / "observed" / "hosts.json"),
            "probed_hosts": 4,
            "healthy_hosts": 3,
            "down_hosts": 1,
            "source": "tcp_probe",
        }

    monkeypatch.setattr("proxy_platform.web_app.refresh_host_observations", fake_refresh)

    response = client.post("/api/observations/refresh")

    assert response.status_code == 200
    assert response.json()["refresh"]["probed_hosts"] == 4
    assert response.json()["refresh"]["healthy_hosts"] == 3
    assert response.json()["refresh"]["down_hosts"] == 1


def test_web_app_rejects_public_mode_when_host_registry_is_private(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path))

    response = client.get("/api/hosts")

    assert response.status_code == 500
    assert response.json()["detail"] == "public host console snapshot is not configured for mode public"


def test_web_app_rejects_invalid_public_snapshot(tmp_path: Path) -> None:
    public_dir = tmp_path / "state" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "host_console.json").write_text(
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
    (public_dir / "subscriptions.json").write_text(
        """
{
  "generated_at": "2026-04-15T00:00:00Z",
  "profile_name": "GG Proxy Nodes",
  "multi_node_url": "https://example.com/subscriptions/v2ray_nodes.txt",
  "multi_node_hiddify_import": "hiddify://import/test#GG",
  "remote_profile_url": "https://example.com/subscriptions/singbox-client-profile.json",
  "per_node": []
}
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
  supported_modes: [public]
repos: []
state_sources:
  - id: public_host_console_snapshot
    display_name: Public Host Console Snapshot
    description: sanitized public host console
    kind: public_host_console_snapshot
    repo_id: proxy-platform
    path: state/public/host_console.json
    ownership: public_projection
    required_modes: [public]
  - id: public_subscription_snapshot
    display_name: Public Subscription Snapshot
    description: sanitized public subscriptions
    kind: public_subscription_snapshot
    repo_id: proxy-platform
    path: state/public/subscriptions.json
    ownership: public_projection
    required_modes: [public]
projections:
  - id: public_host_console
    display_name: Public Host Console
    description: public host view
    kind: public_host_console_projection
    source_ids: [public_host_console_snapshot]
    required_modes: [public]
    rules: {}
  - id: public_subscription_nodes
    display_name: Public Subscription View
    description: public subscription view
    kind: public_subscription_projection
    source_ids: [public_subscription_snapshot]
    required_modes: [public]
    rules: {}
commands: {}
""",
        encoding="utf-8",
    )

    client = TestClient(create_app(manifest_path, tmp_path, mode="public"))
    response = client.get("/api/hosts")

    assert response.status_code == 500
    assert response.json()["detail"].endswith("must define a boolean should_publish")


def test_web_app_applies_authority_handoff_job(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    plan_response = client.post(
        "/api/jobs/plan",
        json={"job_kind": "deploy_host", "payload": {"name": "lisahost"}},
    )
    assert plan_response.status_code == 200
    assert plan_response.json()["plan"]["apply_supported"] is True
    assert plan_response.json()["plan"]["authority_adapter_id"] == "remote_proxy_cliproxy_plus_standalone"

    apply_response = client.post(
        "/api/jobs/apply",
        json={"plan_path": plan_response.json()["plan"]["plan_path"], "confirm": True},
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["result"]["status"] == "applied"
    assert apply_response.json()["result"]["executor"] == "authority_handoff"
    assert apply_response.json()["result"]["handoff_path"].endswith(".yaml")


def test_web_app_applies_decommission_authority_handoff_job(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    plan_response = client.post(
        "/api/jobs/plan",
        json={"job_kind": "decommission_host", "payload": {"name": "lisahost"}},
    )
    assert plan_response.status_code == 200
    assert plan_response.json()["plan"]["authority_adapter_id"] == "remote_proxy_cliproxy_plus_standalone_decommission"

    apply_response = client.post(
        "/api/jobs/apply",
        json={"plan_path": plan_response.json()["plan"]["plan_path"], "confirm": True},
    )
    assert apply_response.status_code == 200
    handoff_path = Path(apply_response.json()["result"]["handoff_path"])
    handoff_payload = yaml.safe_load(handoff_path.read_text(encoding="utf-8"))
    assert handoff_payload["adapter"]["handoff_method"] == "runbook_only"
    assert handoff_payload["recommended_command"] is None



def test_web_app_rejects_authority_handoff_apply_when_required_files_are_missing(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    plan_response = client.post(
        "/api/jobs/plan",
        json={"job_kind": "deploy_host", "payload": {"name": "lisahost"}},
    )
    assert plan_response.status_code == 200

    (tmp_path / "repos" / "remote_proxy" / "config" / "cliproxy-plus.env").unlink()
    apply_response = client.post(
        "/api/jobs/apply",
        json={"plan_path": plan_response.json()["plan"]["plan_path"], "confirm": True},
    )

    assert apply_response.status_code == 409
    assert "authority prerequisites missing" in apply_response.json()["detail"]



def test_web_app_read_only_endpoints_still_work_without_jobs_config(tmp_path: Path) -> None:
    operator_dir = tmp_path / "operator"
    operator_dir.mkdir(parents=True)
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
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))

    hosts_response = client.get("/api/hosts")
    providers_response = client.get("/api/providers")
    overview_response = client.get("/")
    hosts_page = client.get("/hosts")
    subscriptions_page = client.get("/subscriptions")
    providers_page = client.get("/providers")
    jobs_page = client.get("/jobs")
    audit_page = client.get("/audit")
    jobs_response = client.get("/api/jobs")

    assert hosts_response.status_code == 200
    assert providers_response.status_code == 200
    assert overview_response.status_code == 200
    assert hosts_page.status_code == 200
    assert subscriptions_page.status_code == 200
    assert providers_page.status_code == 200
    assert jobs_page.status_code == 404
    assert audit_page.status_code == 404
    assert "只保留只读视图" in overview_response.text
    assert jobs_response.status_code == 500


def test_web_app_rejects_apply_for_plan_outside_managed_directory(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))
    rogue_plan = tmp_path / "rogue-plan.json"
    rogue_plan.write_text("{}", encoding="utf-8")

    response = client.post("/api/jobs/apply", json={"plan_path": str(rogue_plan), "confirm": True})

    assert response.status_code == 409
    assert "plan path must stay inside" in response.json()["detail"]


def test_web_app_rejects_malformed_plan_file_inside_managed_directory(tmp_path: Path) -> None:
    manifest_path = _write_fixture(tmp_path)
    client = TestClient(create_app(manifest_path, tmp_path, mode="operator"))
    managed_plan = tmp_path / "state" / "jobs" / "plans" / "broken.json"
    managed_plan.parent.mkdir(parents=True, exist_ok=True)
    managed_plan.write_text("{not-json", encoding="utf-8")

    response = client.post("/api/jobs/apply", json={"plan_path": str(managed_plan), "confirm": True})

    assert response.status_code == 409
    assert "failed to load plan file" in response.json()["detail"]
