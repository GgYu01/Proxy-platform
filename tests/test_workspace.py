from pathlib import Path

import yaml

from proxy_platform.manifest import load_manifest
from proxy_platform.workspace import collect_repo_statuses, diagnose_workspace
from proxy_platform.workspace import initialize_workspace
from proxy_platform.workspace import sync_workspace


def test_collect_repo_statuses_reports_local_override_availability(tmp_path: Path) -> None:
    repos_root = tmp_path / "repos"
    repos_root.mkdir()
    (repos_root / "remote_proxy").mkdir()
    (repos_root / "cliproxy-control-plane").mkdir()

    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")
    statuses = collect_repo_statuses(manifest, tmp_path, mode="public")
    status_map = {status.repo_id: status for status in statuses}

    assert status_map["remote_proxy"].selected_path == repos_root / "remote_proxy"
    assert status_map["remote_proxy"].exists is True
    assert status_map["cliproxy_control_plane"].selected_path == repos_root / "cliproxy-control-plane"
    assert status_map["cliproxy_control_plane"].exists is True


def test_diagnose_workspace_flags_missing_required_repo(tmp_path: Path) -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")

    diagnosis = diagnose_workspace(manifest, tmp_path, mode="public")

    assert diagnosis.ok is False
    assert any(item.repo_id == "remote_proxy" for item in diagnosis.missing_required)


def test_initialize_workspace_creates_symlinks_from_local_overrides(tmp_path: Path) -> None:
    remote_proxy_src = tmp_path / "sources" / "remote_proxy"
    control_plane_src = tmp_path / "sources" / "cliproxy-control-plane"
    remote_proxy_src.mkdir(parents=True)
    control_plane_src.mkdir(parents=True)

    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_payload = {
        "platform": {
            "name": "proxy-platform",
            "version": "0.1.0",
            "default_mode": "public",
            "supported_modes": ["public", "operator"],
        },
        "repos": [
            {
                "id": "remote_proxy",
                "display_name": "remote_proxy",
                "role": "public_runtime_baseline",
                "required_modes": ["public"],
                "optional": False,
                "visibility": "public",
                "default_url": "https://example.com/remote_proxy.git",
                "default_path": "repos/remote_proxy",
                "local_override_path": str(remote_proxy_src),
            },
            {
                "id": "cliproxy_control_plane",
                "display_name": "CliProxy-control-plane",
                "role": "northbound_control_plane",
                "required_modes": ["public"],
                "optional": False,
                "visibility": "public",
                "default_url": "https://example.com/control-plane.git",
                "default_path": "repos/cliproxy-control-plane",
                "local_override_path": str(control_plane_src),
            },
        ],
        "commands": {},
    }
    manifest_path.write_text(yaml.safe_dump(manifest_payload, sort_keys=False), encoding="utf-8")

    manifest = load_manifest(manifest_path)
    plan = initialize_workspace(manifest, tmp_path, mode="public")

    remote_proxy_dest = tmp_path / "repos" / "remote_proxy"
    control_plane_dest = tmp_path / "repos" / "cliproxy-control-plane"

    assert remote_proxy_dest.is_symlink()
    assert control_plane_dest.is_symlink()
    assert remote_proxy_dest.resolve() == remote_proxy_src.resolve()
    assert control_plane_dest.resolve() == control_plane_src.resolve()
    assert any("linked remote_proxy" in item for item in plan)


def test_sync_workspace_restores_missing_repo_from_local_override(tmp_path: Path) -> None:
    source_repo = tmp_path / "sources" / "remote_proxy"
    source_repo.mkdir(parents=True)

    manifest_path = tmp_path / "platform.manifest.yaml"
    manifest_payload = {
        "platform": {
            "name": "proxy-platform",
            "version": "0.1.0",
            "default_mode": "public",
            "supported_modes": ["public"],
        },
        "repos": [
            {
                "id": "remote_proxy",
                "display_name": "remote_proxy",
                "role": "public_runtime_baseline",
                "required_modes": ["public"],
                "optional": False,
                "visibility": "public",
                "default_url": "https://example.com/remote_proxy.git",
                "default_path": "repos/remote_proxy",
                "local_override_path": str(source_repo),
            }
        ],
        "commands": {},
    }
    manifest_path.write_text(yaml.safe_dump(manifest_payload, sort_keys=False), encoding="utf-8")

    manifest = load_manifest(manifest_path)
    sync_workspace(manifest, tmp_path, mode="public")

    repo_path = tmp_path / "repos" / "remote_proxy"
    assert repo_path.is_symlink()
    assert repo_path.resolve() == source_repo.resolve()
