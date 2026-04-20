#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-gaoyx@112.28.134.53}"
REMOTE_PORT="${REMOTE_PORT:-52117}"
REMOTE_INFRA_ROOT="${REMOTE_INFRA_ROOT:-/mnt/hdo/infra-core}"
MODULE_NAME="proxy-platform-operator"
MODULE_PATH="${REMOTE_INFRA_ROOT}/modules/${MODULE_NAME}"
REGISTER_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/register_module.sh"
HEALTH_URL="${HEALTH_URL:-https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/health}"
HEALTHCHECK_ATTEMPTS="${HEALTHCHECK_ATTEMPTS:-25}"
HEALTHCHECK_INTERVAL_SEC="${HEALTHCHECK_INTERVAL_SEC:-2}"
ENABLE_AUTO_ROLLBACK="${ENABLE_AUTO_ROLLBACK:-0}"

# Optional auto rollback:
#   ENABLE_AUTO_ROLLBACK=1 ./deploy/infra-core-module/redeploy_with_rollback.sh
# Optional health tuning:
#   HEALTHCHECK_ATTEMPTS=20 HEALTHCHECK_INTERVAL_SEC=3 ./deploy/infra-core-module/redeploy_with_rollback.sh

ssh_remote() {
  ssh -p "${REMOTE_PORT}" "${REMOTE_HOST}" "$@"
}

current_image() {
  ssh_remote "python3 - <<'PY'
from pathlib import Path

env_path = Path('${MODULE_PATH}/.env')
if not env_path.exists():
    raise SystemExit(0)
for line in env_path.read_text(encoding='utf-8').splitlines():
    if line.startswith('PROXY_PLATFORM_OPERATOR_IMAGE='):
        print(line.split('=', 1)[1])
        break
PY"
}

latest_backup() {
  ssh_remote "ls -1t '${MODULE_PATH}/.deploy-backups'/source-*.tgz 2>/dev/null | head -n1 || true"
}

set_remote_image() {
  local image_name="$1"
  ssh_remote "python3 - <<'PY'
from pathlib import Path

env_path = Path('${MODULE_PATH}/.env')
lines = env_path.read_text(encoding='utf-8').splitlines()
updated = []
seen = False
for line in lines:
    if line.startswith('PROXY_PLATFORM_OPERATOR_IMAGE='):
        updated.append('PROXY_PLATFORM_OPERATOR_IMAGE=${image_name}')
        seen = True
    else:
        updated.append(line)
if not seen:
    updated.append('PROXY_PLATFORM_OPERATOR_IMAGE=${image_name}')
env_path.write_text('\\n'.join(updated) + '\\n', encoding='utf-8')
PY"
}

wait_for_health() {
  local attempt
  for attempt in $(seq 1 "${HEALTHCHECK_ATTEMPTS}"); do
    local http_code
    http_code="$(curl -sk -o /tmp/proxy-platform-health.json -w '%{http_code}' "${HEALTH_URL}" || true)"
    if [[ "${http_code}" == "200" ]] && grep -q '"status":"ok"' /tmp/proxy-platform-health.json; then
      cat /tmp/proxy-platform-health.json
      return 0
    fi
    sleep "${HEALTHCHECK_INTERVAL_SEC}"
  done
  return 1
}

PREVIOUS_IMAGE="$(current_image || true)"
PREVIOUS_BACKUP="$(latest_backup || true)"

echo "previous image: ${PREVIOUS_IMAGE:-<none>}"
echo "latest backup: ${PREVIOUS_BACKUP:-<none>}"

"${REGISTER_SCRIPT}"
ssh_remote "cd '${REMOTE_INFRA_ROOT}' && scripts/modulectl.sh up ${MODULE_NAME}"

if wait_for_health; then
  echo "deploy health check passed"
  exit 0
fi

echo "deploy health check failed"

if [[ "${ENABLE_AUTO_ROLLBACK}" != "1" ]]; then
  echo "auto rollback disabled; leave ENABLE_AUTO_ROLLBACK=1 to enable it"
  exit 1
fi

if [[ -z "${PREVIOUS_IMAGE}" && -z "${PREVIOUS_BACKUP}" ]]; then
  echo "rollback unavailable: no previous image or backup found" >&2
  exit 1
fi

echo "starting rollback"

if [[ -n "${PREVIOUS_BACKUP}" ]]; then
  ssh_remote "tar -xzf '${PREVIOUS_BACKUP}' -C '${MODULE_PATH}'"
fi

if [[ -n "${PREVIOUS_IMAGE}" ]]; then
  set_remote_image "${PREVIOUS_IMAGE}"
fi

ssh_remote "cd '${REMOTE_INFRA_ROOT}' && scripts/modulectl.sh up ${MODULE_NAME}"

if wait_for_health; then
  echo "rollback recovered the service"
  exit 1
fi

echo "rollback finished but health check is still failing" >&2
exit 1
