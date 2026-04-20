from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from proxy_platform.control_plane_read_model import HttpControlPlaneReadClient
from proxy_platform.runtime_bootstrap import bootstrap_runtime_workspace
from proxy_platform.web_app import run_web_console

PLACEHOLDER_BASIC_AUTH_PASSWORDS = frozenset({"change-me-before-production"})


@dataclass(frozen=True)
class RuntimeSettings:
    manifest_path: Path
    workspace_root: Path
    seed_root: Path
    mode: str
    host: str
    port: int
    basic_auth_username: str
    basic_auth_password: str
    control_plane_base_url: str | None
    control_plane_username: str | None
    control_plane_password: str | None
    control_plane_timeout_seconds: float


def load_runtime_settings(env: Mapping[str, str] | None = None) -> RuntimeSettings:
    values = dict(os.environ if env is None else env)
    basic_auth_username = values.get("PROXY_PLATFORM_WEB_BASIC_AUTH_USERNAME", "").strip()
    basic_auth_password = values.get("PROXY_PLATFORM_WEB_BASIC_AUTH_PASSWORD", "").strip()
    control_plane_base_url = values.get("PROXY_PLATFORM_CONTROL_PLANE_BASE_URL", "").strip().rstrip("/")
    control_plane_username = values.get("PROXY_PLATFORM_CONTROL_PLANE_USERNAME", "").strip()
    control_plane_password = values.get("PROXY_PLATFORM_CONTROL_PLANE_PASSWORD", "").strip()
    if not basic_auth_username or not basic_auth_password:
        raise RuntimeError(
            "basic auth credentials are required for deployed operator runtime; "
            "set PROXY_PLATFORM_WEB_BASIC_AUTH_USERNAME and PROXY_PLATFORM_WEB_BASIC_AUTH_PASSWORD"
        )
    if basic_auth_password in PLACEHOLDER_BASIC_AUTH_PASSWORDS:
        raise RuntimeError(
            "placeholder basic auth password is not allowed for deployed operator runtime; "
            "set a real PROXY_PLATFORM_WEB_BASIC_AUTH_PASSWORD before startup"
        )
    if any((control_plane_base_url, control_plane_username, control_plane_password)) and not all(
        (control_plane_base_url, control_plane_username, control_plane_password)
    ):
        raise RuntimeError(
            "control-plane read access requires PROXY_PLATFORM_CONTROL_PLANE_BASE_URL, "
            "PROXY_PLATFORM_CONTROL_PLANE_USERNAME and PROXY_PLATFORM_CONTROL_PLANE_PASSWORD together"
        )
    return RuntimeSettings(
        manifest_path=Path(values.get("PROXY_PLATFORM_RUNTIME_MANIFEST", "/app/platform.manifest.yaml")).resolve(),
        workspace_root=Path(values.get("PROXY_PLATFORM_RUNTIME_WORKSPACE_ROOT", "/runtime/workspace")).resolve(),
        seed_root=Path(values.get("PROXY_PLATFORM_RUNTIME_SEED_ROOT", "/runtime/seed")).resolve(),
        mode=values.get("PROXY_PLATFORM_WEB_MODE", "operator"),
        host=values.get("PROXY_PLATFORM_WEB_HOST", "0.0.0.0"),
        port=int(values.get("PROXY_PLATFORM_WEB_PORT", "8765")),
        basic_auth_username=basic_auth_username,
        basic_auth_password=basic_auth_password,
        control_plane_base_url=control_plane_base_url or None,
        control_plane_username=control_plane_username or None,
        control_plane_password=control_plane_password or None,
        control_plane_timeout_seconds=float(
            values.get("PROXY_PLATFORM_CONTROL_PLANE_TIMEOUT_SECONDS", "10")
        ),
    )


def main() -> None:
    settings = load_runtime_settings()
    control_plane_read_client = None
    if settings.control_plane_base_url:
        control_plane_read_client = HttpControlPlaneReadClient(
            base_url=settings.control_plane_base_url,
            username=str(settings.control_plane_username),
            password=str(settings.control_plane_password),
            timeout_seconds=settings.control_plane_timeout_seconds,
        )

    bootstrap_runtime_workspace(seed_root=settings.seed_root, workspace_root=settings.workspace_root)
    run_web_console(
        manifest_path=settings.manifest_path,
        workspace_root=settings.workspace_root,
        mode=settings.mode,
        host=settings.host,
        port=settings.port,
        basic_auth_username=settings.basic_auth_username,
        basic_auth_password=settings.basic_auth_password,
        control_plane_read_client=control_plane_read_client,
    )


if __name__ == "__main__":
    main()
