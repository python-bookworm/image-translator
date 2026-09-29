#!/usr/bin/env bash
set -euo pipefail

# Start, stop, restart, or inspect the image translator from the project root.
# The Python executable is taken directly from the Conda environment, matching
# the existing restart-web.sh convention.

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_PATH="${CONDA_ENV_PATH:-/data1/softsevice/anaconda3/envs/cp}"
PYTHON_BIN="${PYTHON_BIN:-${CONDA_ENV_PATH}/bin/python}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/.env.native}"
PID_FILE="${PID_FILE:-${PROJECT_DIR}/image-translator.pid}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/image-translator.log}"
ACTION="${1:-start}"

cd "${PROJECT_DIR}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Conda environment Python not found or not executable: ${PYTHON_BIN}" >&2
  echo "Expected Conda environment: ${CONDA_ENV_PATH}" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Environment file not found: ${ENV_FILE}" >&2
  echo "Create it from .env.native.example before starting the service." >&2
  exit 1
fi

if [[ ! -f "${PROJECT_DIR}/run.py" ]]; then
  echo "Project entry point not found: ${PROJECT_DIR}/run.py" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

process_matches_project() {
  local pid="$1"
  [[ -r "/proc/${pid}/cmdline" ]] || return 1
  tr '\0' ' ' <"/proc/${pid}/cmdline" | grep -F -- "${PROJECT_DIR}/run.py" >/dev/null
}

read_pid() {
  [[ -f "${PID_FILE}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "${pid}"
}

stop_service() {
  local pid
  if ! pid="$(read_pid)"; then
    rm -f -- "${PID_FILE}"
    echo "Image translator is not running."
    return 0
  fi

  if ! kill -0 "${pid}" 2>/dev/null || ! process_matches_project "${pid}"; then
    echo "Removing stale PID file: ${PID_FILE}"
    rm -f -- "${PID_FILE}"
    return 0
  fi

  echo "Stopping image translator: PID ${pid}"
  kill -TERM "${pid}"
  for _ in {1..15}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f -- "${PID_FILE}"
      echo "Image translator stopped."
      return 0
    fi
    sleep 1
  done

  echo "Process did not stop gracefully; sending SIGKILL."
  kill -KILL "${pid}" 2>/dev/null || true
  rm -f -- "${PID_FILE}"
  echo "Image translator stopped."
}

status_service() {
  local pid
  if pid="$(read_pid)" && kill -0 "${pid}" 2>/dev/null && process_matches_project "${pid}"; then
    echo "Image translator is running: PID ${pid}"
    echo "Log file: ${LOG_FILE}"
    return 0
  fi
  echo "Image translator is not running."
  return 1
}

case "${ACTION}" in
  stop)
    stop_service
    exit 0
    ;;
  status)
    status_service
    exit $?
    ;;
  restart)
    stop_service
    ;;
  start)
    ;;
  *)
    echo "Usage: $0 [start|restart|stop|status]" >&2
    exit 2
    ;;
esac

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  if [[ "${old_pid}" =~ ^[0-9]+$ ]] && kill -0 "${old_pid}" 2>/dev/null && process_matches_project "${old_pid}"; then
    echo "Image translator is already running: PID ${old_pid}" >&2
    echo "Use '$0 restart' to restart it." >&2
    echo "Log file: ${LOG_FILE}" >&2
    exit 1
  fi
  rm -f -- "${PID_FILE}"
fi

mkdir -p -- "${LOG_DIR}"

echo "Checking models and Linux runtime..."
"${PYTHON_BIN}" "${PROJECT_DIR}/scripts/validate_models.py" --models "${PROJECT_DIR}/models"
"${PYTHON_BIN}" scripts/check_linux_runtime.py

printf '%s\n' "Starting image translator in background..."
printf 'Project: %s\nPython: %s\nLog: %s\n' "${PROJECT_DIR}" "${PYTHON_BIN}" "${LOG_FILE}"

nohup "${PYTHON_BIN}" -u "${PROJECT_DIR}/run.py" >>"${LOG_FILE}" 2>&1 &
service_pid=$!
printf '%s\n' "${service_pid}" >"${PID_FILE}"

sleep 2
if ! kill -0 "${service_pid}" 2>/dev/null; then
  echo "Service exited during startup. Check log: ${LOG_FILE}" >&2
  rm -f -- "${PID_FILE}"
  exit 1
fi

echo "Image translator started successfully: PID ${service_pid}"
echo "Health check: curl http://127.0.0.1:${APP_PORT:-8080}/health"
echo "Follow log: tail -f ${LOG_FILE}"
