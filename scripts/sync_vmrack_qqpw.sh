#!/usr/bin/env bash
# Thin platform wrapper: delegates vmrack/qqpw dual-egress sync to private ops.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PRIVATE_SYNC="${ROOT_DIR}/repos/proxy_ops_private/scripts/sync_vmrack_qqpw.sh"

if [[ ! -x "${PRIVATE_SYNC}" && ! -f "${PRIVATE_SYNC}" ]]; then
  echo "[ERROR] missing private sync script: ${PRIVATE_SYNC}" >&2
  exit 1
fi

exec bash "${PRIVATE_SYNC}" "$@"
