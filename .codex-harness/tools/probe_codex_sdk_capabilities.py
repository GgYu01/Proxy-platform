#!/usr/bin/env python3
"""Compare official Codex SDK packages for harness provider planning.

The probe is intentionally shallow: it does not start a model run, print
credentials, or assume Codex authentication. It records whether the current
public TypeScript and Python SDK packages expose goal-related surfaces and which
one the harness should keep as its single Codex SDK adapter direction.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JSON = dict[str, Any]
DEFAULT_NODE_PACKAGE = "@openai/codex-sdk"
DEFAULT_PYTHON_PACKAGE = "openai-codex"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_command(args: list[str], *, cwd: Path | None = None, timeout: int = 30) -> JSON:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"available": False, "error": "command_not_found"}
    except PermissionError:
        return {"available": False, "error": "permission_denied"}
    except subprocess.TimeoutExpired:
        return {"available": False, "error": "timeout"}
    return {
        "available": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def npm_package_metadata(package_name: str) -> JSON:
    npm = shutil.which("npm")
    if not npm:
        return {"available": False, "error": "npm_not_found"}
    result = run_command([npm, "view", package_name, "version", "types", "dependencies", "engines", "--json"], timeout=45)
    if not result.get("available"):
        return {"available": False, "error": result.get("error") or result.get("stderr") or "npm_view_failed"}
    try:
        parsed = json.loads(result["stdout"])
    except json.JSONDecodeError:
        parsed = result["stdout"]
    if isinstance(parsed, str):
        return {"available": True, "version": parsed, "types": None}
    return {"available": True, **parsed}


def npm_installed_probe(package_name: str) -> JSON:
    npm = shutil.which("npm")
    if not npm:
        return {"installed": False, "error": "npm_not_found"}
    global_result = run_command([npm, "ls", "-g", package_name, "--depth=0", "--json"], timeout=20)
    local_result = run_command([npm, "ls", package_name, "--depth=0", "--json"], timeout=20) if Path("package.json").exists() else {"available": False, "skipped": "no local package.json"}

    def _has_package(result: JSON) -> bool:
        try:
            parsed = json.loads(result.get("stdout", "{}"))
        except json.JSONDecodeError:
            return False
        dependencies = parsed.get("dependencies") if isinstance(parsed, dict) else None
        return isinstance(dependencies, dict) and package_name in dependencies

    return {
        "global_installed": _has_package(global_result),
        "local_installed": _has_package(local_result),
        "global_probe_returncode": global_result.get("returncode"),
        "local_probe_returncode": local_result.get("returncode"),
    }


def pip_package_metadata(package_name: str) -> JSON:
    result = run_command(
        [sys_executable(), "-m", "pip", "index", "versions", package_name, "--pre", "-i", "https://pypi.org/simple"],
        timeout=45,
    )
    if not result.get("available"):
        return {"available": False, "error": result.get("error") or result.get("stderr") or "pip_index_failed"}
    first_line = result["stdout"].splitlines()[0] if result.get("stdout") else ""
    match = re.search(r"\(([^)]+)\)", first_line)
    return {
        "available": True,
        "version": match.group(1) if match else None,
        "pre_release_query_required": "b" in (match.group(1) if match else ""),
        "raw_head": first_line,
    }


def installed_distribution_probe(package_name: str) -> JSON:
    result = run_command([sys_executable(), "-m", "pip", "show", package_name], timeout=15)
    if not result.get("available"):
        return {"installed": False, "error": result.get("stderr") or result.get("stdout") or result.get("error")}
    info: JSON = {"installed": True}
    for line in result.get("stdout", "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower().replace("-", "_")
        if normalized_key in {"name", "version", "location", "requires"}:
            info[normalized_key] = value.strip()
    return info


def python_runtime_dependency_probe() -> JSON:
    spec = importlib.util.find_spec("codex_cli_bin")
    return {"installed": spec is not None, "origin": spec.origin if spec else None}


def codex_bin_override_probe() -> JSON:
    candidates = [
        os.environ.get("CODEX_BIN"),
        str(Path(".tmp") / "codex-runtime" / "codex.exe"),
    ]
    checked: list[JSON] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).resolve()
        if not path.exists():
            checked.append({"path": str(path), "exists": False})
            continue
        version = run_command([str(path), "--version"], timeout=15)
        checked.append({"path": str(path), "exists": True, "version_probe": version})
    usable = [item for item in checked if item.get("version_probe", {}).get("available")]
    return {"available": bool(usable), "checked": checked, "selected_path": usable[0]["path"] if usable else None}


def python_app_server_initialize_probe(codex_bin_path: str | None) -> JSON:
    if not codex_bin_path:
        return {"available": False, "error": "codex_bin_missing"}
    script = (
        "from openai_codex.client import CodexClient, CodexConfig\n"
        "client = CodexClient(CodexConfig(codex_bin=r'''" + codex_bin_path + "''', cwd=r'''" + str(Path.cwd()) + "'''))\n"
        "try:\n"
        "    client.start()\n"
        "    client.initialize()\n"
        "    print('initialized')\n"
        "finally:\n"
        "    client.close()\n"
    )
    result = run_command([sys_executable(), "-c", script], timeout=30)
    return {"available": result.get("available", False), "result": result}


def sys_executable() -> str:
    return sys.executable


def inspect_node_sdk_types(package_name: str, workdir: Path) -> JSON:
    npm = shutil.which("npm")
    if not npm:
        return {"available": False, "error": "npm_not_found"}
    workdir.mkdir(parents=True, exist_ok=True)
    pack_result = run_command([npm, "pack", package_name, "--pack-destination", str(workdir)], timeout=60)
    if not pack_result.get("available"):
        return {"available": False, "error": pack_result.get("error") or pack_result.get("stderr") or "npm_pack_failed"}
    tarballs = sorted(workdir.glob("*.tgz"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not tarballs:
        return {"available": False, "error": "tarball_missing"}
    extract_dir = workdir / "package"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    with tarfile.open(tarballs[0], "r:gz") as archive:
        archive.extractall(workdir, filter="data")
    dts_path = extract_dir / "dist" / "index.d.ts"
    if not dts_path.exists():
        return {"available": False, "error": "types_missing", "tarball": str(tarballs[0])}
    text = dts_path.read_text(encoding="utf-8")
    public_goal_mentions = sorted(set(re.findall(r"\bgoal\b|thread/goal/[a-z]+", text, flags=re.IGNORECASE)))
    has_thread_working_directory = "workingDirectory?: string" in text
    has_start_thread = "startThread" in text
    has_resume_thread = "resumeThread" in text
    return {
        "available": True,
        "language": "typescript_node",
        "types_path": str(dts_path),
        "has_high_level_goal_api": bool(public_goal_mentions),
        "goal_mentions": public_goal_mentions,
        "has_thread_working_directory": has_thread_working_directory,
        "has_start_thread": has_start_thread,
        "has_resume_thread": has_resume_thread,
    }


def inspect_python_sdk_wheel(package_name: str, version: str | None, workdir: Path) -> JSON:
    workdir.mkdir(parents=True, exist_ok=True)
    package_spec = f"{package_name}=={version}" if version else package_name
    download = run_command(
        [
            sys_executable(),
            "-m",
            "pip",
            "download",
            package_spec,
            "--pre",
            "--no-deps",
            "-d",
            str(workdir),
            "-i",
            "https://pypi.org/simple",
        ],
        timeout=60,
    )
    if not download.get("available"):
        return {"available": False, "error": download.get("error") or download.get("stderr") or "pip_download_failed"}
    wheels = sorted(workdir.glob("*.whl"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not wheels:
        return {"available": False, "error": "wheel_missing"}
    extract_dir = workdir / "wheel"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    with zipfile.ZipFile(wheels[0]) as archive:
        archive.extractall(extract_dir)

    generated = extract_dir / "openai_codex" / "generated" / "v2_all.py"
    client = extract_dir / "openai_codex" / "client.py"
    api = extract_dir / "openai_codex" / "api.py"
    metadata = next(extract_dir.glob("openai_codex-*.dist-info/METADATA"), None)
    generated_text = generated.read_text(encoding="utf-8") if generated.exists() else ""
    client_text = client.read_text(encoding="utf-8") if client.exists() else ""
    api_text = api.read_text(encoding="utf-8") if api.exists() else ""
    metadata_text = metadata.read_text(encoding="utf-8") if metadata else ""
    return {
        "available": True,
        "language": "python",
        "wheel_path": str(wheels[0]),
        "has_typed_package_marker": (extract_dir / "openai_codex" / "py.typed").exists(),
        "has_sync_api": "class Codex:" in api_text,
        "has_async_api": "class AsyncCodex:" in api_text,
        "has_low_level_json_rpc_request": "def request(" in client_text,
        "uses_pinned_codex_runtime_dependency": "openai-codex-cli-bin" in client_text or "openai-codex-cli-bin" in metadata_text,
        "has_cwd_thread_start": "cwd: str | None = None" in api_text,
        "has_generated_goal_requests": all(
            marker in generated_text
            for marker in ("thread/goal/set", "thread/goal/get", "thread/goal/clear", "ThreadGoalSetRequest")
        ),
        "has_collab_agent_thread_items": "CollabAgentToolCallThreadItem" in generated_text,
    }


def python_module_probe(module_names: list[str]) -> JSON:
    modules: JSON = {}
    for name in module_names:
        spec = importlib.util.find_spec(name)
        modules[name] = {"available": spec is not None, "origin": spec.origin if spec else None}
    return modules


def codex_cli_probe() -> JSON:
    path = shutil.which("codex")
    if not path:
        return {"available": False, "error": "codex_not_found"}
    version = run_command([path, "--version"], timeout=15)
    return {"path": path, "version_probe": version}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-package", default=DEFAULT_NODE_PACKAGE)
    parser.add_argument("--python-package", default=DEFAULT_PYTHON_PACKAGE)
    parser.add_argument("--inspect-remote-packages", action="store_true")
    parser.add_argument("--workdir", type=Path, default=Path(".tmp") / "codex-sdk-probe")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(dir=args.workdir.parent if args.workdir.parent.exists() else None) as temp_dir:
        inspect_dir = Path(temp_dir) / "npm"
        python_inspect_dir = Path(temp_dir) / "pypi"
        node_sdk_types = inspect_node_sdk_types(args.node_package, inspect_dir) if args.inspect_remote_packages else {"available": None, "skipped": "pass --inspect-remote-packages"}
        python_metadata = pip_package_metadata(args.python_package) if args.inspect_remote_packages else {"available": None, "skipped": "pass --inspect-remote-packages"}
        python_sdk_wheel = (
            inspect_python_sdk_wheel(args.python_package, python_metadata.get("version"), python_inspect_dir)
            if args.inspect_remote_packages
            else {"available": None, "skipped": "pass --inspect-remote-packages"}
        )
        installed_python_sdk = installed_distribution_probe(args.python_package)
        installed_runtime_dependency = installed_distribution_probe("openai-codex-cli-bin")
        codex_bin_override = codex_bin_override_probe()
        app_server_initialize = python_app_server_initialize_probe(codex_bin_override.get("selected_path"))
        receipt: JSON = {
            "packet_type": "codex_sdk_capability_probe",
            "created_at": now_iso(),
            "typescript_sdk": {
                "package": args.node_package,
                "metadata": npm_package_metadata(args.node_package),
                "installed_distribution": npm_installed_probe(args.node_package),
                "api_surface": node_sdk_types,
                "decision": "not_selected_for_harness_adapter",
                "reason": "public_types_do_not_expose_goal_requests_or_low_level_app_server_rpc",
            },
            "python_sdk": {
                "package": args.python_package,
                "metadata": python_metadata,
                "installed_distribution": installed_python_sdk,
                "runtime_dependency_distribution": installed_runtime_dependency,
                "runtime_dependency_module": python_runtime_dependency_probe(),
                "codex_bin_override": codex_bin_override,
                "app_server_initialize_probe": app_server_initialize,
                "api_surface": python_sdk_wheel,
                "decision": "selected_for_harness_adapter",
                "reason": "official_beta_package_exposes_typed_generated_goal_requests_and_low_level_json_rpc_request",
            },
            "python_modules": python_module_probe(["openai_codex", "codex", "openai", "agents", "openai_agents"]),
            "codex_cli": codex_cli_probe(),
            "conclusion": {
                "selected_sdk_language": "python",
                "selected_official_package": args.python_package,
                "discarded_sdk_language": "typescript_node",
                "discarded_official_package": args.node_package,
                "goal_integration_strategy": "sync_harness_goal_state_with_python_sdk_generated_thread_goal_requests_after_local_probe",
                "adapter_policy": "keep_one_codex_sdk_adapter_python_only",
            },
        }
        text = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
