from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Callable

from proxy_platform.manifest import PythonRequirement
from proxy_platform.manifest import ToolchainCommandSpec
from proxy_platform.manifest import ToolchainProfile


WhichFunc = Callable[[str], str | None]
RunFunc = Callable[[list[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class OsRelease:
    system_id: str
    version_id: str
    pretty_name: str


@dataclass(frozen=True)
class PythonDiagnosis:
    min_version: str
    env_hint: str | None
    checked_commands: list[str]
    selected_command: str | None
    selected_path: str | None
    version: str | None
    ok: bool


@dataclass(frozen=True)
class CommandDiagnosis:
    command_id: str
    display_name: str
    ok: bool
    selected_argv: list[str] | None
    version: str | None
    detail: str | None


@dataclass(frozen=True)
class ToolchainDiagnosis:
    profile_id: str
    display_name: str
    description: str
    os_release: OsRelease
    python: PythonDiagnosis
    commands: list[CommandDiagnosis]
    ok: bool


def diagnose_toolchain_profile(
    profile: ToolchainProfile,
    *,
    os_release_path: str | Path = "/etc/os-release",
    which: WhichFunc = shutil.which,
    run: RunFunc | None = None,
) -> ToolchainDiagnosis:
    runner = run or _run_command
    os_release = read_os_release(os_release_path)
    python_diagnosis = diagnose_python_requirement(profile.python, which=which, run=runner)
    command_diagnoses = [diagnose_command_requirement(command, which=which, run=runner) for command in profile.commands]
    ok = python_diagnosis.ok and all(command.ok for command in command_diagnoses)
    return ToolchainDiagnosis(
        profile_id=profile.profile_id,
        display_name=profile.display_name,
        description=profile.description,
        os_release=os_release,
        python=python_diagnosis,
        commands=command_diagnoses,
        ok=ok,
    )


def read_os_release(path: str | Path) -> OsRelease:
    values: dict[str, str] = {}
    file_path = Path(path)
    if file_path.exists():
        for raw_line in file_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    system_id = values.get("ID", "unknown")
    version_id = values.get("VERSION_ID", "unknown")
    pretty_name = values.get("PRETTY_NAME", f"{system_id} {version_id}")
    return OsRelease(system_id=system_id, version_id=version_id, pretty_name=pretty_name)


def diagnose_python_requirement(
    requirement: PythonRequirement,
    *,
    which: WhichFunc,
    run: RunFunc,
) -> PythonDiagnosis:
    checked_commands: list[str] = []
    for command_name in requirement.candidates:
        resolved = which(command_name)
        if not resolved:
            continue
        checked_commands.append(command_name)
        completed = run([resolved, "--version"])
        version = extract_version(completed.stdout) or extract_version(completed.stderr)
        if completed.returncode != 0 or not version:
            continue
        if version_satisfies_minimum(version, requirement.min_version):
            return PythonDiagnosis(
                min_version=requirement.min_version,
                env_hint=requirement.env_hint,
                checked_commands=checked_commands,
                selected_command=command_name,
                selected_path=resolved,
                version=version,
                ok=True,
            )
    return PythonDiagnosis(
        min_version=requirement.min_version,
        env_hint=requirement.env_hint,
        checked_commands=checked_commands,
        selected_command=None,
        selected_path=None,
        version=None,
        ok=False,
    )


def diagnose_command_requirement(
    requirement: ToolchainCommandSpec,
    *,
    which: WhichFunc,
    run: RunFunc,
) -> CommandDiagnosis:
    candidates = [requirement.argv, *requirement.fallback_argvs]
    last_detail: str | None = None
    for argv in candidates:
        resolved_argv = resolve_argv(argv, which=which)
        if resolved_argv is None:
            continue
        completed = run(resolved_argv)
        version = summarize_output(completed.stdout, completed.stderr)
        if completed.returncode == 0:
            return CommandDiagnosis(
                command_id=requirement.command_id,
                display_name=requirement.display_name,
                ok=True,
                selected_argv=resolved_argv,
                version=version,
                detail=None,
            )
        last_detail = version or f"exit={completed.returncode}"
    return CommandDiagnosis(
        command_id=requirement.command_id,
        display_name=requirement.display_name,
        ok=False,
        selected_argv=None,
        version=None,
        detail=last_detail or "missing",
    )


def resolve_argv(argv: list[str], *, which: WhichFunc) -> list[str] | None:
    resolved = which(argv[0])
    if not resolved:
        return None
    return [resolved, *argv[1:]]


def version_satisfies_minimum(version: str, minimum: str) -> bool:
    candidate_tuple = normalize_version(version)
    minimum_tuple = normalize_version(minimum)
    width = max(len(candidate_tuple), len(minimum_tuple))
    padded_candidate = candidate_tuple + (0,) * (width - len(candidate_tuple))
    padded_minimum = minimum_tuple + (0,) * (width - len(minimum_tuple))
    return padded_candidate >= padded_minimum


def normalize_version(value: str) -> tuple[int, ...]:
    match = re.search(r"\d+(?:\.\d+)+", value)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(0).split("."))


def extract_version(output: str) -> str | None:
    match = re.search(r"\d+(?:\.\d+)+", output)
    if not match:
        return None
    return match.group(0)


def summarize_output(stdout: str, stderr: str) -> str | None:
    for stream in (stdout, stderr):
        lines = [line.strip() for line in stream.splitlines() if line.strip()]
        if lines:
            return lines[0]
    return None


def _run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, capture_output=True, text=True)
