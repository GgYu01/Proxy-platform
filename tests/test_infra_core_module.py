from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_operator_module_compose_exposes_healthcheck_gateway_and_direct_port() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    service = compose["services"]["proxy-platform-operator"]

    assert service["env_file"] == ["./.env"]
    assert service["ports"] == ["${PROXY_PLATFORM_OPERATOR_HOST_PORT:-18082}:8765"]
    assert "infra_gateway_net" in service["networks"]
    assert "healthcheck" in service
    assert any(label == "traefik.enable=true" for label in service["labels"])
    assert any("proxy-platform-operator.svc.prod.lab.gglohh.top" in label for label in service["labels"])


def test_operator_module_env_example_declares_runtime_seed_and_auth_inputs() -> None:
    env_example = (ROOT / "deploy" / "infra-core-module" / "module.env.example").read_text(encoding="utf-8")

    assert "PROXY_PLATFORM_OPERATOR_IMAGE=" in env_example
    assert "PROXY_PLATFORM_OPERATOR_PUBLIC_HOST=" in env_example
    assert "PROXY_PLATFORM_OPERATOR_BASIC_AUTH_USERNAME=admin" in env_example
    assert "PROXY_PLATFORM_OPERATOR_BASIC_AUTH_PASSWORD=" in env_example


def test_operator_module_dockerfile_uses_mainland_mirror_sources() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "docker.m.daocloud.io/library/python:3.12.8-slim-bookworm" in dockerfile
    assert "mirrors.aliyun.com/pypi/simple" in dockerfile
    assert "ARG APT_MIRROR_URL=https://mirrors.aliyun.com" in dockerfile
    assert "deb ${APT_MIRROR_URL}/debian bookworm main" in dockerfile
    assert "deb ${APT_MIRROR_URL}/debian-security bookworm-security main" in dockerfile


def test_register_module_script_keeps_runtime_workspace_and_seed_separate() -> None:
    script = (ROOT / "deploy" / "infra-core-module" / "register_module.sh").read_text(encoding="utf-8")

    assert ".runtime-workspace" in script
    assert ".runtime-seed" in script
    assert "--exclude '.env'" in script
    assert "registry.list" in script
    assert "proxy-platform-operator" in script


def test_register_module_script_updates_image_after_successful_build() -> None:
    script = (ROOT / "deploy" / "infra-core-module" / "register_module.sh").read_text(encoding="utf-8")

    assert script.index("docker build ${DOCKER_BUILD_ARGS} -t '${IMAGE_NAME}' .") < script.index(
        "updated.append('PROXY_PLATFORM_OPERATOR_IMAGE=${IMAGE_NAME}')"
    )


def test_register_module_script_passes_mainland_mirror_build_args() -> None:
    script = (ROOT / "deploy" / "infra-core-module" / "register_module.sh").read_text(encoding="utf-8")

    assert "--build-arg PYTHON_BASE_IMAGE=" in script
    assert "--build-arg PIP_INDEX_URL=" in script
    assert "--build-arg PIP_TRUSTED_HOST=" in script
    assert "--build-arg APT_MIRROR_URL=" in script


def test_register_module_script_uses_dirty_suffix_for_uncommitted_worktree() -> None:
    script = (ROOT / "deploy" / "infra-core-module" / "register_module.sh").read_text(encoding="utf-8")

    assert "status --short --untracked-files=normal" in script
    assert "dirty-" in script


def test_register_module_script_refreshes_runtime_truth_only_when_workspace_still_matches_previous_seed() -> None:
    script = (ROOT / "deploy" / "infra-core-module" / "register_module.sh").read_text(encoding="utf-8")

    assert "SEED_BACKUP_DIR" in script
    assert "refresh_runtime_truth_from_seed" in script
    assert "docker run --rm" in script
    assert "/runtime/previous-seed:ro" in script


def test_redeploy_script_supports_optional_auto_rollback() -> None:
    script = (ROOT / "deploy" / "infra-core-module" / "redeploy_with_rollback.sh").read_text(encoding="utf-8")

    assert "ENABLE_AUTO_ROLLBACK" in script
    assert "PREVIOUS_IMAGE" in script
    assert 'HEALTHCHECK_ATTEMPTS="${HEALTHCHECK_ATTEMPTS:-25}"' in script
    assert "scripts/modulectl.sh up ${MODULE_NAME}" in script
    assert "rollback" in script
    assert "curl -sk" in script
