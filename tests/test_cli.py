from io import StringIO
from pathlib import Path
import subprocess

import pytest

from proxy_platform.cli import run_cli
from proxy_platform.toolchain import CommandDiagnosis
from proxy_platform.toolchain import OsRelease
from proxy_platform.toolchain import PythonDiagnosis
from proxy_platform.toolchain import ToolchainDiagnosis


def test_manifest_validate_command_prints_ok() -> None:
    stdout = StringIO()
    exit_code = run_cli(
        ["manifest", "validate", "--manifest", str(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")],
        stdout=stdout,
    )
    output = stdout.getvalue()

    assert exit_code == 0
    assert "manifest: ok" in output


def test_repos_list_command_includes_required_repo_ids(tmp_path: Path) -> None:
    (tmp_path / "repos").mkdir()
    stdout = StringIO()

    exit_code = run_cli(
        [
            "repos",
            "list",
            "--manifest",
            str(Path(__file__).resolve().parents[1] / "platform.manifest.yaml"),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "public",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "remote_proxy" in output
    assert "cliproxy_control_plane" in output


def test_init_dry_run_command_emits_plan(tmp_path: Path) -> None:
    stdout = StringIO()

    exit_code = run_cli(
        [
            "init",
            "--manifest",
            str(Path(__file__).resolve().parents[1] / "platform.manifest.yaml"),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
            "--dry-run",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "dry-run" in output
    assert "proxy_ops_private" in output


def test_doctor_returns_non_zero_when_required_repo_missing(tmp_path: Path) -> None:
    stdout = StringIO()

    exit_code = run_cli(
        [
            "doctor",
            "--manifest",
            str(Path(__file__).resolve().parents[1] / "platform.manifest.yaml"),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "public",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 1
    assert "missing required repos" in output
    assert "remote_proxy" in output


def test_doctor_toolchain_command_prints_profile_status(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = Path(__file__).resolve().parents[1] / "platform.manifest.yaml"
    stdout = StringIO()

    monkeypatch.setattr(
        "proxy_platform.cli.diagnose_toolchain_profile",
        lambda profile, **kwargs: ToolchainDiagnosis(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            description=profile.description,
            os_release=OsRelease(system_id="debian", version_id="11", pretty_name="Debian GNU/Linux 11"),
            python=PythonDiagnosis(
                min_version="3.9",
                env_hint="REMOTE_PROXY_PYTHON_BIN",
                checked_commands=["python3.11"],
                selected_command="python3.11",
                selected_path="/usr/bin/python3.11",
                version="3.11.8",
                ok=True,
            ),
            commands=[
                CommandDiagnosis(
                    command_id="curl",
                    display_name="curl",
                    ok=True,
                    selected_argv=["/usr/bin/curl", "--version"],
                    version="curl 8.5.0",
                    detail=None,
                )
            ],
            ok=True,
        ),
    )

    exit_code = run_cli(
        [
            "doctor",
            "toolchain",
            "--manifest",
            str(manifest_path),
            "--profile",
            "cliproxy_plus_standalone",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "doctor-toolchain: profile=cliproxy_plus_standalone ok=true" in output
    assert "os: Debian GNU/Linux 11" in output
    assert "python: ok=true min=3.9 selected=python3.11 path=/usr/bin/python3.11 version=3.11.8" in output
    assert "- curl: ok=true version=curl 8.5.0" in output


def test_doctor_toolchain_returns_non_zero_when_profile_not_satisfied(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = Path(__file__).resolve().parents[1] / "platform.manifest.yaml"
    stdout = StringIO()

    monkeypatch.setattr(
        "proxy_platform.cli.diagnose_toolchain_profile",
        lambda profile, **kwargs: ToolchainDiagnosis(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            description=profile.description,
            os_release=OsRelease(system_id="debian", version_id="10", pretty_name="Debian GNU/Linux 10"),
            python=PythonDiagnosis(
                min_version="3.11",
                env_hint="CLIPROXY_CONTROL_PLANE_PYTHON_BIN",
                checked_commands=["python3"],
                selected_command=None,
                selected_path=None,
                version=None,
                ok=False,
            ),
            commands=[
                CommandDiagnosis(
                    command_id="docker",
                    display_name="docker",
                    ok=False,
                    selected_argv=None,
                    version=None,
                    detail="missing",
                )
            ],
            ok=False,
        ),
    )

    exit_code = run_cli(
        [
            "doctor",
            "toolchain",
            "--manifest",
            str(manifest_path),
            "--profile",
            "control_plane_compose",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 2
    assert "doctor-toolchain: profile=control_plane_compose ok=false" in output
    assert "- docker: ok=false detail=missing" in output


def test_sync_dry_run_command_emits_repo_actions(tmp_path: Path) -> None:
    stdout = StringIO()

    exit_code = run_cli(
        [
            "sync",
            "--manifest",
            str(Path(__file__).resolve().parents[1] / "platform.manifest.yaml"),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "public",
            "--dry-run",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "dry-run: sync workspace" in output


def test_hosts_list_command_prints_expected_and_observed_state(tmp_path: Path) -> None:
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

    stdout = StringIO()
    exit_code = run_cli(
        [
            "hosts",
            "list",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "hosts: total=1 publishable=1" in output
    assert "lisahost" in output
    assert "observed=healthy" in output
    assert "publish=true" in output


def test_subscriptions_list_command_prints_multi_and_per_node_urls(tmp_path: Path) -> None:
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
  default_mode: public
  supported_modes: [public, operator]
repos: []
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    required_modes: [operator]
commands: {}
""",
        encoding="utf-8",
    )

    stdout = StringIO()
    exit_code = run_cli(
        [
            "subscriptions",
            "list",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "multi_node_url=https://example.com/subscriptions/v2ray_nodes.txt" in output
    assert "lisahost" in output
    assert "v2ray_url=https://example.com/subscriptions/v2ray_node_lisahost.txt" in output


def test_hosts_list_command_rejects_public_mode_when_registry_is_operator_only(tmp_path: Path) -> None:
    operator_dir = tmp_path / "operator"
    operator_dir.mkdir(parents=True)
    (operator_dir / "nodes.yaml").write_text("nodes: []\n", encoding="utf-8")
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
  default_mode: public
  supported_modes: [public, operator]
repos: []
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    required_modes: [operator]
commands: {}
""",
        encoding="utf-8",
    )

    stdout = StringIO()
    stderr = StringIO()
    exit_code = run_cli(
        [
            "hosts",
            "list",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert "host registry source is not configured for mode public" in stderr.getvalue()


def test_providers_list_command_prints_timeout_and_retry_budgets(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public]
repos: []
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
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

    stdout = StringIO()
    exit_code = run_cli(
        [
            "providers",
            "list",
            "--manifest",
            str(manifest_path),
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "providers: total=1" in output
    assert "local_mcp_pool" in output
    assert "startup_timeout=15" in output
    assert "request_attempts=2" in output

    assert "cliproxy_control_plane" in output


def test_hosts_list_command_projects_registry_and_observations(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
hosts:
  - host_id: lisahost
    display_name: Lisahost
    endpoint: https://lisa.example.com/sub
    provider: cliproxy_plus
    enabled: true
    include_in_subscription: true
""",
        encoding="utf-8",
    )
    observations_path = tmp_path / "observations.yaml"
    observations_path.write_text(
        """
observations:
  - host_id: lisahost
    status: healthy
    source: probe
""",
        encoding="utf-8",
    )
    stdout = StringIO()

    exit_code = run_cli(
        [
            "hosts",
            "--registry",
            str(registry_path),
            "--observations",
            str(observations_path),
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "lisahost" in output
    assert "desired=enabled" in output
    assert "observed=healthy" in output
    assert "subscription=true" in output


def test_subscriptions_preview_command_reports_members_and_exclusions(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text(
        """
hosts:
  - host_id: lisahost
    display_name: Lisahost
    endpoint: https://lisa.example.com/sub
    provider: cliproxy_plus
    enabled: true
    include_in_subscription: true
  - host_id: drain
    display_name: Drain
    endpoint: https://drain.example.com/sub
    provider: cliproxy_plus
    enabled: false
    include_in_subscription: true
""",
        encoding="utf-8",
    )
    observations_path = tmp_path / "observations.yaml"
    observations_path.write_text(
        """
observations:
  - host_id: lisahost
    status: down
    source: agent
  - host_id: stray
    status: healthy
    source: probe
""",
        encoding="utf-8",
    )
    stdout = StringIO()

    exit_code = run_cli(
        [
            "subscriptions",
            "preview",
            "--registry",
            str(registry_path),
            "--observations",
            str(observations_path),
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "subscription-preview: members=1" in output
    assert "- lisahost:" in output
    assert "observed=down" in output
    assert "excluded hosts: drain" in output
    assert "unknown observation hosts: stray" in output


def test_jobs_plan_add_host_and_apply_commands_create_audited_inventory_change(tmp_path: Path) -> None:
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
    host_spec_path = tmp_path / "vmrack1.json"
    host_spec_path.write_text(
        """
{
  "name": "vmrack1",
  "host": "38.65.93.39",
  "ssh_port": 22,
  "base_port": 10000,
  "subscription_alias": "GG-Vmrack1",
  "enabled": true,
  "infra_core_candidate": true,
  "change_policy": "mutable",
  "provider": "vmrack"
}
""",
        encoding="utf-8",
    )
    plan_path = tmp_path / "state" / "jobs" / "plans" / "add-host.json"

    stdout = StringIO()
    exit_code = run_cli(
        [
            "jobs",
            "plan-add-host",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
            "--spec",
            str(host_spec_path),
            "--output",
            str(plan_path),
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "job planned:" in output
    assert "kind=add_host" in output
    assert plan_path.exists()

    stdout = StringIO()
    exit_code = run_cli(
        [
            "jobs",
            "apply",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
            "--plan-file",
            str(plan_path),
            "--confirm",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "job applied:" in output
    assert "status=applied" in output


def test_jobs_apply_rejects_dry_run_only_deploy_job(tmp_path: Path) -> None:
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
    plan_path = tmp_path / "state" / "jobs" / "plans" / "deploy-host.json"

    stdout = StringIO()
    exit_code = run_cli(
        [
            "jobs",
            "plan-deploy-host",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
            "--host-name",
            "lisahost",
            "--output",
            str(plan_path),
        ],
        stdout=stdout,
    )
    assert exit_code == 0
    assert plan_path.exists()

    stdout = StringIO()
    stderr = StringIO()
    exit_code = run_cli(
        [
            "jobs",
            "apply",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
            "--plan-file",
            str(plan_path),
            "--confirm",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert "dry-run only in current phase" in stderr.getvalue()


def test_jobs_apply_rejects_plan_file_outside_managed_directory(tmp_path: Path) -> None:
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
  jobs:
    audit_path: state/jobs/audit
    required_modes: [operator]
    require_confirmation: true
    kinds:
      - id: add_host
        allow_apply: true
        executor: inventory_only
commands: {}
""",
        encoding="utf-8",
    )
    rogue_plan = tmp_path / "rogue-plan.json"
    rogue_plan.write_text("{}", encoding="utf-8")

    stdout = StringIO()
    stderr = StringIO()
    exit_code = run_cli(
        [
            "jobs",
            "apply",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
            "--plan-file",
            str(rogue_plan),
            "--confirm",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert "plan path must stay inside" in stderr.getvalue()


def test_jobs_apply_reports_missing_managed_plan_file_cleanly(tmp_path: Path) -> None:
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
  jobs:
    audit_path: state/jobs/audit
    required_modes: [operator]
    require_confirmation: true
    kinds:
      - id: add_host
        allow_apply: true
        executor: inventory_only
commands: {}
""",
        encoding="utf-8",
    )
    missing_plan = tmp_path / "state" / "jobs" / "plans" / "missing.json"

    stdout = StringIO()
    stderr = StringIO()
    exit_code = run_cli(
        [
            "jobs",
            "apply",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "operator",
            "--plan-file",
            str(missing_plan),
            "--confirm",
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert "unknown plan file" in stderr.getvalue()


def test_init_without_dry_run_links_local_override_repo(tmp_path: Path) -> None:
    source_repo = tmp_path / "sources" / "remote_proxy"
    source_repo.mkdir(parents=True)
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public]
repos:
  - id: remote_proxy
    display_name: remote_proxy
    role: public_runtime_baseline
    required_modes: [public]
    optional: false
    visibility: public
    default_url: https://example.com/remote_proxy.git
    default_path: repos/remote_proxy
    local_override_path: REPLACE_SOURCE
commands: {}
""".replace("REPLACE_SOURCE", str(source_repo)),
        encoding="utf-8",
    )
    stdout = StringIO()

    exit_code = run_cli(
        [
            "init",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "public",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "linked remote_proxy" in output
    assert (tmp_path / "repos" / "remote_proxy").is_symlink()


def test_manifest_validate_returns_error_for_invalid_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: broken
  supported_modes: [public]
repos: []
commands: {}
""",
        encoding="utf-8",
    )
    stdout = StringIO()

    exit_code = run_cli(
        ["manifest", "validate", "--manifest", str(manifest_path)],
        stdout=stdout,
    )

    assert exit_code == 2


def test_init_returns_error_when_repo_cannot_be_materialized(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public]
repos:
  - id: remote_proxy
    display_name: remote_proxy
    role: public_runtime_baseline
    required_modes: [public]
    optional: false
    visibility: public
    default_url: https://example.com/remote_proxy.git
    default_path: repos/remote_proxy
commands: {}
""",
        encoding="utf-8",
    )
    stdout = StringIO()

    exit_code = run_cli(
        [
            "init",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "public",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 2
    assert "failed to clone remote_proxy" in output


def test_sync_returns_error_when_existing_git_repo_fetch_fails(tmp_path: Path) -> None:
    source_repo = tmp_path / "sources" / "remote_proxy"
    source_repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    (source_repo / "README.md").write_text("remote proxy\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_repo, check=True, capture_output=True, text=True)

    repo_path = tmp_path / "repos" / "remote_proxy"
    repo_path.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", str(source_repo), str(repo_path)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "remote", "set-url", "origin", "https://example.com/remote_proxy.git"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )

    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        f"""
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public]
repos:
  - id: remote_proxy
    display_name: remote_proxy
    role: public_runtime_baseline
    required_modes: [public]
    optional: false
    visibility: public
    default_url: {source_repo}
    default_path: repos/remote_proxy
commands: {{}}
""",
        encoding="utf-8",
    )
    stdout = StringIO()

    exit_code = run_cli(
        [
            "sync",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "public",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 2
    assert "failed to fetch remote_proxy" in output


def test_init_clones_local_git_repo_when_no_override_exists(tmp_path: Path) -> None:
    source_repo = tmp_path / "sources" / "remote_proxy"
    source_repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    (source_repo / "README.md").write_text("remote proxy\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=source_repo, check=True, capture_output=True, text=True)

    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        f"""
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public]
repos:
  - id: remote_proxy
    display_name: remote_proxy
    role: public_runtime_baseline
    required_modes: [public]
    optional: false
    visibility: public
    default_url: {source_repo}
    default_path: repos/remote_proxy
commands: {{}}
""",
        encoding="utf-8",
    )
    stdout = StringIO()

    exit_code = run_cli(
        [
            "init",
            "--manifest",
            str(manifest_path),
            "--workspace-root",
            str(tmp_path),
            "--mode",
            "public",
        ],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert exit_code == 0
    assert "cloned remote_proxy" in output
    assert (tmp_path / "repos" / "remote_proxy" / "README.md").exists()
