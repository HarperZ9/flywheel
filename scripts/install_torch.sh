#!/usr/bin/env bash
# Install the CUDA build of torch into the E: venv. Long pole #1.
# Runs standalone so it can be backgrounded and is safe to re-run (idempotent).
set -uo pipefail
RUN=/e/local-model-run
PY="$RUN/venv/Scripts/python.exe"
export PIP_CACHE_DIR='E:\local-model-run\pip-cache'
export TMP='E:\local-model-run\tmp'
export TEMP='E:\local-model-run\tmp'
mkdir -p "$RUN/tmp" "$RUN/logs"
LOG="$RUN/logs/install-torch.log"
{
  echo "=== $(date) install torch (cu124) START ==="
  "$PY" -m pip install --upgrade pip setuptools wheel
  "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cu124
  rc=$?
  echo "=== $(date) pip rc=$rc ==="
  "$PY" -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no-cuda'))"
  echo "=== $(date) install torch DONE (verify rc=$?) ==="
} >> "$LOG" 2>&1
