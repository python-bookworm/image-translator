#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/image-translator-poc}"
PYTHON_BIN="${PYTHON_BIN:-python}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.native}"

cd "${PROJECT_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file not found: ${ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

"${PYTHON_BIN}" scripts/validate_models.py --models "${PROJECT_DIR}/models"
"${PYTHON_BIN}" scripts/check_linux_runtime.py
exec "${PYTHON_BIN}" run.py

