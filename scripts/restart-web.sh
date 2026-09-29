#!/bin/bash

# ====================== 必须修改这里 ======================
CONDA_ENV_PATH="/data1/softsevice/anaconda3/envs/file_compare"
PYTHON_SCRIPT="web_app.py"
# ==========================================================

LOG_DIR="./logs"
LOG_FILE="${LOG_DIR}/app.log"

cd "$(dirname "$0")" || exit

echo "===== 重启应用 ====="

# 关闭旧进程
pkill -f $PYTHON_SCRIPT
sleep 2

# 启动新进程
VENV_PYTHON="${CONDA_ENV_PATH}/bin/python"
nohup $VENV_PYTHON -u $PYTHON_SCRIPT > $LOG_FILE 2>&1 &

echo "重启成功！新PID：$!"
echo "查看日志：tail -f $LOG_FILE"
