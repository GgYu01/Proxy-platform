from pathlib import Path
import subprocess

from proxy_platform.manifest import load_manifest
from proxy_platform.toolchain import diagnose_toolchain_profile
from proxy_platform.toolchain import version_satisfies_minimum


def test_version_satisfies_minimum_compares_numeric_segments() -> None:
    assert version_satisfies_minimum("3.11.2", "3.11") is True
    assert version_satisfies_minimum("3.10.9", "3.11") is False
    assert version_satisfies_minimum("3.9.18", "3.9") is True


def test_diagnose_toolchain_profile_selects_first_matching_python_candidate(tmp_path: Path) -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")
    profile = manifest.toolchains["cliproxy_plus_standalone"]
    os_release_path = tmp_path / "os-release"
    os_release_path.write_text('ID=debian\nVERSION_ID="11"\nPRETTY_NAME="Debian GNU/Linux 11"\n', encoding="utf-8")

    def fake_which(command_name: str) -> str | None:
        mapping = {
            "python3.11": "/usr/bin/python3.11",
            "python3.10": "/usr/bin/python3.10",
            "curl": "/usr/bin/curl",
            "jq": "/usr/bin/jq",
            "podman": "/usr/bin/podman",
            "systemctl": "/usr/bin/systemctl",
        }
        return mapping.get(command_name)

    def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        output_map = {
            ("/usr/bin/python3.11", "--version"): "Python 3.11.8\n",
            ("/usr/bin/python3.10", "--version"): "Python 3.10.14\n",
            ("/usr/bin/curl", "--version"): "curl 8.5.0\n",
            ("/usr/bin/jq", "--version"): "jq-1.7\n",
            ("/usr/bin/podman", "--version"): "podman version 5.0.0\n",
            ("/usr/bin/systemctl", "--version"): "systemd 252\n",
        }
        key = tuple(argv)
        if key not in output_map:
            raise AssertionError(f"unexpected argv: {argv}")
        return subprocess.CompletedProcess(argv, 0, output_map[key], "")

    diagnosis = diagnose_toolchain_profile(
        profile,
        os_release_path=os_release_path,
        which=fake_which,
        run=fake_run,
    )

    assert diagnosis.ok is True
    assert diagnosis.os_release.pretty_name == "Debian GNU/Linux 11"
    assert diagnosis.python.selected_command == "python3.11"
    assert diagnosis.python.selected_path == "/usr/bin/python3.11"
    assert diagnosis.python.version == "3.11.8"


def test_diagnose_toolchain_profile_uses_fallback_command_when_primary_missing(tmp_path: Path) -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")
    profile = manifest.toolchains["control_plane_compose"]
    os_release_path = tmp_path / "os-release"
    os_release_path.write_text('ID=ubuntu\nVERSION_ID="22.04"\nPRETTY_NAME="Ubuntu 22.04.4 LTS"\n', encoding="utf-8")

    def fake_which(command_name: str) -> str | None:
        mapping = {
            "python3.11": "/usr/bin/python3.11",
            "docker": "/usr/bin/docker",
            "docker-compose": "/usr/local/bin/docker-compose",
        }
        return mapping.get(command_name)

    def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        key = tuple(argv)
        if key == ("/usr/bin/python3.11", "--version"):
            return subprocess.CompletedProcess(argv, 0, "Python 3.11.9\n", "")
        if key == ("/usr/bin/docker", "--version"):
            return subprocess.CompletedProcess(argv, 0, "Docker version 26.1.0, build deadbeef\n", "")
        if key == ("/usr/bin/docker", "compose", "version"):
            return subprocess.CompletedProcess(argv, 1, "", "docker: 'compose' is not a docker command.\n")
        if key == ("/usr/local/bin/docker-compose", "--version"):
            return subprocess.CompletedProcess(argv, 0, "docker-compose version 1.29.2, build 5becea4c\n", "")
        raise AssertionError(f"unexpected argv: {argv}")

    diagnosis = diagnose_toolchain_profile(
        profile,
        os_release_path=os_release_path,
        which=fake_which,
        run=fake_run,
    )

    docker_compose = next(command for command in diagnosis.commands if command.command_id == "docker_compose")
    assert diagnosis.ok is True
    assert docker_compose.ok is True
    assert docker_compose.selected_argv == ["/usr/local/bin/docker-compose", "--version"]
    assert "1.29.2" in (docker_compose.version or "")


def test_diagnose_toolchain_profile_reports_missing_python_and_commands(tmp_path: Path) -> None:
    manifest = load_manifest(Path(__file__).resolve().parents[1] / "platform.manifest.yaml")
    profile = manifest.toolchains["cliproxy_plus_standalone"]
    os_release_path = tmp_path / "os-release"
    os_release_path.write_text('ID=debian\nVERSION_ID="10"\nPRETTY_NAME="Debian GNU/Linux 10"\n', encoding="utf-8")

    def fake_which(command_name: str) -> str | None:
        mapping = {
            "python3": "/usr/bin/python3",
            "curl": "/usr/bin/curl",
        }
        return mapping.get(command_name)

    def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        key = tuple(argv)
        if key == ("/usr/bin/python3", "--version"):
            return subprocess.CompletedProcess(argv, 0, "Python 3.7.3\n", "")
        if key == ("/usr/bin/curl", "--version"):
            return subprocess.CompletedProcess(argv, 0, "curl 7.64.0\n", "")
        raise AssertionError(f"unexpected argv: {argv}")

    diagnosis = diagnose_toolchain_profile(
        profile,
        os_release_path=os_release_path,
        which=fake_which,
        run=fake_run,
    )

    missing_commands = {command.command_id for command in diagnosis.commands if not command.ok}
    assert diagnosis.ok is False
    assert diagnosis.python.ok is False
    assert diagnosis.python.selected_command is None
    assert missing_commands == {"jq", "podman", "systemctl"}
