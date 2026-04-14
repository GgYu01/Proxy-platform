from pathlib import Path

import pytest

from proxy_platform.manifest import load_manifest
from proxy_platform.manifest import ManifestError


def test_load_manifest_requires_expected_repo_roles() -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")

    repo_ids = [repo.repo_id for repo in manifest.repos]
    assert repo_ids == [
        "remote_proxy",
        "cliproxy_control_plane",
        "proxy_ops_private",
        "remote_browser",
    ]
    assert manifest.default_mode == "public"
    assert manifest.supported_modes == ["public", "operator"]

    roles = {repo.repo_id: repo.role for repo in manifest.repos}
    assert roles["remote_proxy"] == "public_runtime_baseline"
    assert roles["cliproxy_control_plane"] == "northbound_control_plane"
    assert roles["proxy_ops_private"] == "private_ops_source_of_truth"
    assert roles["remote_browser"] == "optional_provider"


def test_load_manifest_tracks_visibility_and_required_modes() -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")
    repo_map = {repo.repo_id: repo for repo in manifest.repos}

    assert repo_map["proxy_ops_private"].visibility == "private"
    assert repo_map["proxy_ops_private"].required_modes == ["operator"]
    assert repo_map["remote_proxy"].optional is False


def test_load_manifest_tracks_toolchain_profiles() -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")

    cliproxy_profile = manifest.toolchains["cliproxy_plus_standalone"]
    control_plane_profile = manifest.toolchains["control_plane_compose"]

    assert cliproxy_profile.python.min_version == "3.9"
    assert cliproxy_profile.python.env_hint == "REMOTE_PROXY_PYTHON_BIN"
    assert cliproxy_profile.repo_ids == ["remote_proxy"]
    assert [command.command_id for command in cliproxy_profile.commands] == [
        "curl",
        "jq",
        "podman",
        "systemctl",
    ]

    assert control_plane_profile.python.min_version == "3.11"
    assert control_plane_profile.repo_ids == ["cliproxy_control_plane"]
    docker_compose = next(command for command in control_plane_profile.commands if command.command_id == "docker_compose")
    assert docker_compose.argv == ["docker", "compose", "version"]
    assert docker_compose.fallback_argvs == [["docker-compose", "--version"]]


def test_load_manifest_tracks_state_sources_and_projections() -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")

    host_registry = manifest.state_sources["host_registry"]
    observation = manifest.state_sources["host_observation"]
    subscription_projection = manifest.projections["subscription_nodes"]

    assert manifest.host_registry is not None
    assert manifest.host_registry.required_modes == ["operator"]
    assert host_registry.kind == "host_registry"
    assert host_registry.repo_id == "proxy_ops_private"
    assert host_registry.path == Path("inventory/nodes.yaml")
    assert host_registry.ownership == "private_truth"

    assert observation.kind == "host_observation"
    assert observation.repo_id == "proxy-platform"
    assert observation.path == Path("state/observations/hosts.json")
    assert observation.ownership == "platform_observed_state"

    assert subscription_projection.kind == "subscription_projection"
    assert subscription_projection.source_ids == [
        "host_registry",
        "subscription_policy",
        "host_observation",
    ]
    assert subscription_projection.required_modes == ["operator"]
    assert subscription_projection.rules["include_unhealthy_observed_hosts"] is True
    assert subscription_projection.rules["require_registry_enabled"] is True


def test_load_manifest_tracks_job_policy_and_audit_config() -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")

    assert manifest.jobs is not None
    assert manifest.jobs.audit_path == Path("state/jobs/audit")
    assert manifest.jobs.handoff_path == Path("state/jobs/handoffs")
    assert manifest.jobs.required_modes == ["operator"]
    assert manifest.jobs.require_confirmation is True
    assert manifest.jobs.policy_for("add_host").allow_apply is True
    assert manifest.jobs.policy_for("remove_host").allow_apply is True
    assert manifest.jobs.policy_for("deploy_host").allow_apply is True
    assert manifest.jobs.policy_for("deploy_host").executor == "authority_handoff"
    assert manifest.jobs.policy_for("decommission_host").executor == "authority_handoff"
    assert manifest.authority_adapters["remote_proxy_cliproxy_plus_standalone"].entrypoint == Path(
        "repos/remote_proxy/scripts/service.sh"
    )
    assert manifest.authority_adapters["remote_proxy_cliproxy_plus_standalone"].actions["deploy_host"] == "install"
    assert (
        manifest.authority_adapters["remote_proxy_cliproxy_plus_standalone_decommission"].handoff_method
        == "runbook_only"
    )
    assert manifest.authority_adapters["remote_proxy_cliproxy_plus_infra_core_sidecar"].required_paths == (
        Path("repos/remote_proxy"),
    )
    assert manifest.authority_adapters["remote_proxy_cliproxy_plus_infra_core_sidecar"].downstream_required_paths == (
        Path("/mnt/hdo/infra-core"),
    )


def test_load_manifest_rejects_authority_adapter_with_unknown_repo(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: operator
  supported_modes: [operator]
repos: []
state:
  jobs:
    audit_path: state/jobs/audit
    handoff_path: state/jobs/handoffs
    required_modes: [operator]
    require_confirmation: true
    kinds:
      - id: deploy_host
        allow_apply: true
        executor: authority_handoff
authority_adapters:
  - id: broken
    display_name: broken
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
    required_paths: [repos/remote_proxy]
    required_env_files: [repos/remote_proxy/config/cliproxy-plus.env]
    required_env_keys: [CLIPROXY_IMAGE]
    rollback_owner: remote_proxy
    rollback_hint: rollback
commands: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_rejects_authority_handoff_job_without_adapter(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: operator
  supported_modes: [operator]
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
  jobs:
    audit_path: state/jobs/audit
    handoff_path: state/jobs/handoffs
    required_modes: [operator]
    require_confirmation: true
    kinds:
      - id: deploy_host
        allow_apply: true
        executor: authority_handoff
commands: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_rejects_projection_with_unknown_source(tmp_path: Path) -> None:
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
state_sources:
  - id: host_registry
    display_name: Host Registry
    description: expected hosts
    kind: host_registry
    repo_id: remote_proxy
    path: inventory/nodes.yaml
    ownership: private_truth
    required_modes: [public]
projections:
  - id: broken
    display_name: broken
    description: broken
    kind: subscription_projection
    source_ids: [host_registry, missing_source]
    required_modes: [public]
    rules:
      include_unhealthy_observed_hosts: true
commands: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_rejects_projection_mode_not_supported_by_its_sources(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public, operator]
repos:
  - id: proxy_ops_private
    display_name: Proxy_ops_private
    role: private_ops_source_of_truth
    required_modes: [operator]
    optional: true
    visibility: private
    default_url: git@example.com/private.git
    default_path: repos/proxy_ops_private
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    required_modes: [operator]
state_sources:
  - id: host_registry
    display_name: Host Registry
    description: expected hosts
    kind: host_registry
    repo_id: proxy_ops_private
    path: inventory/nodes.yaml
    ownership: private_truth
    required_modes: [operator]
projections:
  - id: broken_public_projection
    display_name: broken public projection
    description: claims public visibility from private-only source
    kind: host_console_projection
    source_ids: [host_registry]
    required_modes: [public]
    rules: {}
commands: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_rejects_duplicate_repo_ids(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: public
  supported_modes: [public, operator]
repos:
  - id: dup
    display_name: first
    role: a
    required_modes: [public]
    optional: false
    visibility: public
    default_url: https://example.com/a.git
    default_path: repos/a
  - id: dup
    display_name: second
    role: b
    required_modes: [public]
    optional: true
    visibility: public
    default_url: https://example.com/b.git
    default_path: repos/b
commands: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_rejects_duplicate_toolchain_ids(tmp_path: Path) -> None:
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
toolchains:
  - id: same
    display_name: first
    description: first
    required_modes: [public]
    repo_ids: [remote_proxy]
    python:
      min_version: "3.9"
      candidates: [python3]
      env_hint: REMOTE_PROXY_PYTHON_BIN
    commands:
      - id: curl
        display_name: curl
        argv: [curl, --version]
  - id: same
    display_name: second
    description: second
    required_modes: [public]
    repo_ids: [remote_proxy]
    python:
      min_version: "3.11"
      candidates: [python3.11]
      env_hint: REMOTE_PROXY_PYTHON_BIN
    commands:
      - id: jq
        display_name: jq
        argv: [jq, --version]
commands: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_rejects_invalid_default_mode(tmp_path: Path) -> None:
    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_path.write_text(
        """
platform:
  name: proxy-platform
  version: 0.1.0
  default_mode: broken
  supported_modes: [public, operator]
repos: []
commands: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_rejects_toolchain_unknown_repo_id(tmp_path: Path) -> None:
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
toolchains:
  - id: broken_profile
    display_name: broken
    description: broken
    required_modes: [public]
    repo_ids: [missing_repo]
    python:
      min_version: "3.9"
      candidates: [python3]
      env_hint: REMOTE_PROXY_PYTHON_BIN
    commands:
      - id: curl
        display_name: curl
        argv: [curl, --version]
commands: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_rejects_gitmodules_path_mismatch(tmp_path: Path) -> None:
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
    (tmp_path / ".gitmodules").write_text(
        """
[submodule "remote_proxy"]
    path = repos/not-remote-proxy
    url = https://example.com/remote_proxy.git
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_load_manifest_accepts_matching_gitmodules(tmp_path: Path) -> None:
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
    (tmp_path / ".gitmodules").write_text(
        """
[submodule "remote_proxy"]
    path = repos/remote_proxy
    url = https://example.com/remote_proxy.git
""",
        encoding="utf-8",
    )

    manifest = load_manifest(manifest_path)
    assert manifest.repos[0].repo_id == "remote_proxy"


def test_load_manifest_tracks_host_registry_and_local_provider_policies(tmp_path: Path) -> None:
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
    required_modes: [public]
    optional: false
    visibility: public
    default_url: https://example.com/remote_proxy.git
    default_path: repos/remote_proxy
state:
  host_registry:
    inventory_path: operator/nodes.yaml
    subscriptions_path: operator/subscriptions.yaml
    observations_path: state/observed/hosts.json
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

    manifest = load_manifest(manifest_path)

    assert manifest.host_registry is not None
    assert manifest.host_registry.inventory_path == Path("operator/nodes.yaml")
    assert manifest.host_registry.subscriptions_path == Path("operator/subscriptions.yaml")
    assert manifest.host_registry.observations_path == Path("state/observed/hosts.json")
    assert len(manifest.local_providers) == 1
    provider = manifest.local_providers[0]
    assert provider.provider_id == "local_mcp_pool"
    assert provider.kind == "mcp"
    assert provider.startup_timeout_seconds == 15
    assert provider.request_timeout_seconds == 45
    assert provider.startup_max_attempts == 3
    assert provider.request_max_attempts == 2
