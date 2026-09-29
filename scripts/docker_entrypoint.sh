#!/bin/sh
set -eu

python3 scripts/validate_models.py --models /opt/image-translator/models
python3 scripts/check_linux_runtime.py
exec python3 run.py

