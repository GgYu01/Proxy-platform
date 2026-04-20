#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-gaoyx@112.28.134.53}"
REMOTE_PORT="${REMOTE_PORT:-52117}"
REMOTE_INFRA_ROOT="${REMOTE_INFRA_ROOT:-/mnt/hdo/infra-core}"
MODULE_NAME="proxy-platform-operator"
MODULE_PATH="${REMOTE_INFRA_ROOT}/modules/${MODULE_NAME}"
PYTHON_BASE_IMAGE="${PYTHON_BASE_IMAGE:-docker.m.daocloud.io/library/python:3.12.8-slim-bookworm}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-mirrors.aliyun.com}"
APT_MIRROR_URL="${APT_MIRROR_URL:-https://mirrors.aliyun.com}"
DOCKER_BUILD_ARGS="--build-arg PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE} --build-arg PIP_INDEX_URL=${PIP_INDEX_URL} --build-arg PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} --build-arg APT_MIRROR_URL=${APT_MIRROR_URL}"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGISTRY_LINE="${MODULE_NAME}|${MODULE_PATH}|docker-compose.yml|Authenticated proxy-platform operator console"
DEFAULT_IMAGE_TAG="$(
  if git -C "${LOCAL_ROOT}" rev-parse --short=12 HEAD >/dev/null 2>&1; then
    base_tag="$(git -C "${LOCAL_ROOT}" rev-parse --short=12 HEAD)"
    if [[ -n "$(git -C "${LOCAL_ROOT}" status --short --untracked-files=normal 2>/dev/null)" ]]; then
      printf '%s-dirty-%s' "${base_tag}" "$(date +%Y%m%d%H%M%S)"
    else
      printf '%s' "${base_tag}"
    fi
  else
    date +%Y%m%d%H%M%S
  fi
)"
IMAGE_TAG="${IMAGE_TAG:-${DEFAULT_IMAGE_TAG}}"
IMAGE_NAME="${IMAGE_NAME:-proxy-platform-operator:${IMAGE_TAG}}"
TMP_SEED_DIR="$(mktemp -d)"
BACKUP_NAME="source-$(date +%Y%m%dT%H%M%S).tgz"
SEED_BACKUP_DIR="${MODULE_PATH}/.deploy-backups/runtime-seed-${BACKUP_NAME%.tgz}"

cleanup() {
  rm -rf "${TMP_SEED_DIR}"
}
trap cleanup EXIT

mkdir -p \
  "${TMP_SEED_DIR}/operator" \
  "${TMP_SEED_DIR}/state/observations" \
  "${TMP_SEED_DIR}/authority/remote_proxy/scripts" \
  "${TMP_SEED_DIR}/authority/remote_proxy/config" \
  "${TMP_SEED_DIR}/authority/remote_proxy/docs/deploy"

cp "${LOCAL_ROOT}/repos/proxy_ops_private/inventory/nodes.yaml" "${TMP_SEED_DIR}/operator/nodes.yaml"
cp "${LOCAL_ROOT}/repos/proxy_ops_private/inventory/subscriptions.yaml" "${TMP_SEED_DIR}/operator/subscriptions.yaml"
if [[ -f "${LOCAL_ROOT}/state/observations/hosts.json" ]]; then
  cp "${LOCAL_ROOT}/state/observations/hosts.json" "${TMP_SEED_DIR}/state/observations/hosts.json"
fi
cp "${LOCAL_ROOT}/repos/remote_proxy/scripts/service.sh" "${TMP_SEED_DIR}/authority/remote_proxy/scripts/service.sh"
cp "${LOCAL_ROOT}/repos/remote_proxy/config/cliproxy-plus.env" "${TMP_SEED_DIR}/authority/remote_proxy/config/cliproxy-plus.env"
cp "${LOCAL_ROOT}/repos/remote_proxy/docs/deploy/cliproxy-plus-standalone-vps.md" \
  "${TMP_SEED_DIR}/authority/remote_proxy/docs/deploy/cliproxy-plus-standalone-vps.md"
cp "${LOCAL_ROOT}/repos/remote_proxy/docs/deploy/infra-core-ubuntu-online.md" \
  "${TMP_SEED_DIR}/authority/remote_proxy/docs/deploy/infra-core-ubuntu-online.md"

ssh -p "${REMOTE_PORT}" "${REMOTE_HOST}" "mkdir -p \
  '${MODULE_PATH}' \
  '${MODULE_PATH}/.runtime-workspace' \
  '${MODULE_PATH}/.runtime-seed' \
  '${MODULE_PATH}/.deploy-backups'"

ssh -p "${REMOTE_PORT}" "${REMOTE_HOST}" "\
  if [ -f '${MODULE_PATH}/docker-compose.yml' ]; then \
    tar -czf '${MODULE_PATH}/.deploy-backups/${BACKUP_NAME}' \
      --exclude='.runtime-workspace' \
      --exclude='.runtime-seed' \
      --exclude='.deploy-backups' \
      -C '${MODULE_PATH}' .; \
  fi"

ssh -p "${REMOTE_PORT}" "${REMOTE_HOST}" "\
  rm -rf '${SEED_BACKUP_DIR}' && \
  mkdir -p '${SEED_BACKUP_DIR}' && \
  if [ -d '${MODULE_PATH}/.runtime-seed' ]; then \
    cp -a '${MODULE_PATH}/.runtime-seed/.' '${SEED_BACKUP_DIR}/'; \
  fi"

rsync -az --delete \
  -e "ssh -p ${REMOTE_PORT}" \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '.venv_fix' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.env' \
  --exclude 'archive' \
  --exclude 'tmp' \
  --exclude 'state' \
  --exclude 'repos' \
  --exclude '.runtime-workspace' \
  --exclude '.runtime-seed' \
  --exclude '.deploy-backups' \
  "${LOCAL_ROOT}/" "${REMOTE_HOST}:${MODULE_PATH}/"

rsync -az --delete \
  -e "ssh -p ${REMOTE_PORT}" \
  "${TMP_SEED_DIR}/" "${REMOTE_HOST}:${MODULE_PATH}/.runtime-seed/"

ssh -p "${REMOTE_PORT}" "${REMOTE_HOST}" "\
  if [ ! -f '${MODULE_PATH}/.env' ]; then \
    cp '${MODULE_PATH}/deploy/infra-core-module/module.env.example' '${MODULE_PATH}/.env'; \
  fi && \
  if ! grep -Fq '${REGISTRY_LINE}' '${REMOTE_INFRA_ROOT}/modules/registry.list'; then \
    printf '%s\n' '${REGISTRY_LINE}' >> '${REMOTE_INFRA_ROOT}/modules/registry.list'; \
  fi"

ssh -p "${REMOTE_PORT}" "${REMOTE_HOST}" "cd '${MODULE_PATH}' && docker build ${DOCKER_BUILD_ARGS} -t '${IMAGE_NAME}' ."

ssh -p "${REMOTE_PORT}" "${REMOTE_HOST}" "cd '${MODULE_PATH}' && docker run --rm \
  -v \"\$PWD/.runtime-seed:/runtime/current-seed:ro\" \
  -v \"\$PWD/.runtime-workspace:/runtime/workspace\" \
  -v \"\$PWD/.deploy-backups/runtime-seed-${BACKUP_NAME%.tgz}:/runtime/previous-seed:ro\" \
  '${IMAGE_NAME}' \
  python -c \"from proxy_platform.runtime_truth_sync import refresh_runtime_truth_from_seed; result = refresh_runtime_truth_from_seed(previous_seed_root='/runtime/previous-seed', current_seed_root='/runtime/current-seed', workspace_root='/runtime/workspace'); print('runtime truth sync:', {'seeded': list(result.seeded_files), 'refreshed': list(result.refreshed_files), 'preserved': list(result.preserved_files)})\""

ssh -p "${REMOTE_PORT}" "${REMOTE_HOST}" "python3 - <<'PY'
from pathlib import Path

env_path = Path('${MODULE_PATH}/.env')
lines = env_path.read_text(encoding='utf-8').splitlines()
updated = []
seen = False
for line in lines:
    if line.startswith('PROXY_PLATFORM_OPERATOR_IMAGE='):
        updated.append('PROXY_PLATFORM_OPERATOR_IMAGE=${IMAGE_NAME}')
        seen = True
    else:
        updated.append(line)
if not seen:
    updated.append('PROXY_PLATFORM_OPERATOR_IMAGE=${IMAGE_NAME}')
env_path.write_text('\\n'.join(updated) + '\\n', encoding='utf-8')
PY"

echo "Module copied to ${MODULE_PATH}"
echo "Built image: ${IMAGE_NAME}"
echo "Next steps on remote:"
echo "  cd ${MODULE_PATH}"
echo "  vi .env"
echo "  cd ${REMOTE_INFRA_ROOT}"
echo "  scripts/modulectl.sh up ${MODULE_NAME}"
echo
echo "Manual rollback example:"
echo "  tar -xzf ${MODULE_PATH}/.deploy-backups/${BACKUP_NAME} -C ${MODULE_PATH}"
echo "  scripts/modulectl.sh up ${MODULE_NAME}"
