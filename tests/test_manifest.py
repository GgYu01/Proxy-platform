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
