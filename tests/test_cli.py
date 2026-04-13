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
