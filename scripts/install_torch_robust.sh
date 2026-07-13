#!/usr/bin/env bash
# Robust torch install for a flaky link: resumable curl of the wheel (auto
# -resume with -C -), completeness checked via the zip central directory, then
# a single pip install with deps. Loops the fetch until the wheel is intact.
set -uo pipefail
RUN=/e/local-model-run
PY="$RUN/venv/Scripts/python.exe"
export PIP_CACHE_DIR='E:\local-model-run\pip-cache'
export TMP='E:\local-model-run\tmp'; export TEMP='E:\local-model-run\tmp'
export PIP_DEFAULT_TIMEOUT=60
mkdir -p "$RUN/tmp" "$RUN/logs" "$RUN/wheels"
LOG="$RUN/logs/install-torch.log"
WHL_MSYS="$RUN/wheels/torch-2.6.0+cu124-cp312-cp312-win_amd64.whl"
WHL_WIN='E:\local-model-run\wheels\torch-2.6.0+cu124-cp312-cp312-win_amd64.whl'
URL="https://download.pytorch.org/whl/cu124/torch-2.6.0%2Bcu124-cp312-cp312-win_amd64.whl"
{
  echo "=== $(date) ROBUST torch install START ==="
  "$PY" -m pip install --upgrade pip setuptools wheel
  wheel_ok=0
  for attempt in $(seq 1 25); do
    echo "--- fetch attempt $attempt ($(date)) ---"
    curl -L -C - --retry 8 --retry-all-errors --retry-delay 5 \
         --connect-timeout 30 -o "$WHL_MSYS" "$URL" || echo "curl non-zero (resume next loop)"
    sz=$(stat -c %s "$WHL_MSYS" 2>/dev/null || echo 0)
    echo "wheel size: $sz bytes"
    # complete iff the zip central directory (end of file) parses
    if "$PY" -c "import zipfile; zipfile.ZipFile(r'$WHL_WIN').namelist()" 2>/dev/null; then
      echo "wheel intact -> complete"; wheel_ok=1; break
    fi
    echo "wheel incomplete; resuming"; sleep 3
  done
  if [ "$wheel_ok" != "1" ]; then echo "FAILED to fully download wheel"; exit 1; fi
  echo "--- pip install torch (with deps) ---"
  "$PY" -m pip install "$WHL_WIN"
  echo "pip rc=$?"
  "$PY" -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no-cuda'))"
  echo "=== $(date) ROBUST torch install DONE verify_rc=$? ==="
} >> "$LOG" 2>&1
