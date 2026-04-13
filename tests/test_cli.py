from io import StringIO
from pathlib import Path

from proxy_platform.cli import run_cli


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
    assert "cliproxy_control_plane" in output


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

    assert exit_code == 2
