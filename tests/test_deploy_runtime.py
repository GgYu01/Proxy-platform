from pathlib import Path

import pytest

from proxy_platform.deploy_runtime import load_runtime_settings


def test_load_runtime_settings_requires_basic_auth_credentials() -> None:
    with pytest.raises(RuntimeError, match="basic auth"):
        load_runtime_settings(
            {
                "PROXY_PLATFORM_RUNTIME_MANIFEST": "/app/platform.manifest.yaml",
                "PROXY_PLATFORM_RUNTIME_WORKSPACE_ROOT": "/runtime/workspace",
                "PROXY_PLATFORM_RUNTIME_SEED_ROOT": "/runtime/seed",
                "PROXY_PLATFORM_WEB_MODE": "operator",
                "PROXY_PLATFORM_WEB_HOST": "0.0.0.0",
                "PROXY_PLATFORM_WEB_PORT": "8765",
                "PROXY_PLATFORM_WEB_BASIC_AUTH_USERNAME": "operator",
            }
        )


def test_load_runtime_settings_accepts_complete_auth_credentials() -> None:
    settings = load_runtime_settings(
        {
            "PROXY_PLATFORM_RUNTIME_MANIFEST": "/app/platform.manifest.yaml",
            "PROXY_PLATFORM_RUNTIME_WORKSPACE_ROOT": "/runtime/workspace",
            "PROXY_PLATFORM_RUNTIME_SEED_ROOT": "/runtime/seed",
            "PROXY_PLATFORM_WEB_MODE": "operator",
            "PROXY_PLATFORM_WEB_HOST": "0.0.0.0",
            "PROXY_PLATFORM_WEB_PORT": "8765",
            "PROXY_PLATFORM_WEB_BASIC_AUTH_USERNAME": "operator",
            "PROXY_PLATFORM_WEB_BASIC_AUTH_PASSWORD": "secret",
        }
    )

    assert settings.manifest_path == Path("/app/platform.manifest.yaml")
    assert settings.workspace_root == Path("/runtime/workspace")
    assert settings.seed_root == Path("/runtime/seed")
    assert settings.basic_auth_username == "operator"
    assert settings.basic_auth_password == "secret"


def test_load_runtime_settings_rejects_placeholder_password() -> None:
    with pytest.raises(RuntimeError, match="placeholder"):
        load_runtime_settings(
            {
                "PROXY_PLATFORM_RUNTIME_MANIFEST": "/app/platform.manifest.yaml",
                "PROXY_PLATFORM_RUNTIME_WORKSPACE_ROOT": "/runtime/workspace",
                "PROXY_PLATFORM_RUNTIME_SEED_ROOT": "/runtime/seed",
                "PROXY_PLATFORM_WEB_MODE": "operator",
                "PROXY_PLATFORM_WEB_HOST": "0.0.0.0",
                "PROXY_PLATFORM_WEB_PORT": "8765",
                "PROXY_PLATFORM_WEB_BASIC_AUTH_USERNAME": "operator",
                "PROXY_PLATFORM_WEB_BASIC_AUTH_PASSWORD": "change-me-before-production",
            }
        )


def test_load_runtime_settings_accepts_control_plane_read_config() -> None:
    settings = load_runtime_settings(
        {
            "PROXY_PLATFORM_RUNTIME_MANIFEST": "/app/platform.manifest.yaml",
            "PROXY_PLATFORM_RUNTIME_WORKSPACE_ROOT": "/runtime/workspace",
            "PROXY_PLATFORM_RUNTIME_SEED_ROOT": "/runtime/seed",
            "PROXY_PLATFORM_WEB_MODE": "operator",
            "PROXY_PLATFORM_WEB_HOST": "0.0.0.0",
            "PROXY_PLATFORM_WEB_PORT": "8765",
            "PROXY_PLATFORM_WEB_BASIC_AUTH_USERNAME": "operator",
            "PROXY_PLATFORM_WEB_BASIC_AUTH_PASSWORD": "secret",
            "PROXY_PLATFORM_CONTROL_PLANE_BASE_URL": "https://cliproxy-control-plane.example.com",
            "PROXY_PLATFORM_CONTROL_PLANE_USERNAME": "reader",
            "PROXY_PLATFORM_CONTROL_PLANE_PASSWORD": "reader-secret",
            "PROXY_PLATFORM_CONTROL_PLANE_TIMEOUT_SECONDS": "12.5",
        }
    )

    assert settings.control_plane_base_url == "https://cliproxy-control-plane.example.com"
    assert settings.control_plane_username == "reader"
    assert settings.control_plane_password == "reader-secret"
    assert settings.control_plane_timeout_seconds == 12.5


def test_load_runtime_settings_requires_complete_control_plane_read_credentials() -> None:
    with pytest.raises(RuntimeError, match="control-plane read access"):
        load_runtime_settings(
            {
                "PROXY_PLATFORM_RUNTIME_MANIFEST": "/app/platform.manifest.yaml",
                "PROXY_PLATFORM_RUNTIME_WORKSPACE_ROOT": "/runtime/workspace",
                "PROXY_PLATFORM_RUNTIME_SEED_ROOT": "/runtime/seed",
                "PROXY_PLATFORM_WEB_MODE": "operator",
                "PROXY_PLATFORM_WEB_HOST": "0.0.0.0",
                "PROXY_PLATFORM_WEB_PORT": "8765",
                "PROXY_PLATFORM_WEB_BASIC_AUTH_USERNAME": "operator",
                "PROXY_PLATFORM_WEB_BASIC_AUTH_PASSWORD": "secret",
                "PROXY_PLATFORM_CONTROL_PLANE_BASE_URL": "https://cliproxy-control-plane.example.com",
                "PROXY_PLATFORM_CONTROL_PLANE_USERNAME": "reader",
            }
        )
