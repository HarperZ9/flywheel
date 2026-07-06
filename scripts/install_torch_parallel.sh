#!/usr/bin/env bash
# Torch install via multi-connection ranged download (beats pytorch CDN
# per-connection throttling), then verify + pip install. Resumable.
set -uo pipefail
RUN=/e/local-model-run
PY="$RUN/venv/Scripts/python.exe"
export PIP_CACHE_DIR='E:\local-model-run\pip-cache'
export TMP='E:\local-model-run\tmp'; export TEMP='E:\local-model-run\tmp'
mkdir -p "$RUN/tmp" "$RUN/logs" "$RUN/wheels"
LOG="$RUN/logs/install-torch.log"
WHL_WIN='E:\local-model-run\wheels\torch-2.6.0+cu124-cp312-cp312-win_amd64.whl'
PARTS='E:\local-model-run\wheels\parts'
URL="https://download.pytorch.org/whl/cu124/torch-2.6.0%2Bcu124-cp312-cp312-win_amd64.whl"
{
  echo "=== $(date) PARALLEL torch download START ==="
  for attempt in $(seq 1 6); do
    echo "--- parallel attempt $attempt ($(date)) ---"
    "$PY" "C:/dev/local-model/scripts/download_parallel.py" \
        --url "$URL" --out "$WHL_WIN" --parts-dir "$PARTS" --conns 16
    [ "$?" = "0" ] && break
    echo "retrying assembly/parts"; sleep 3
  done
  if "$PY" -c "import zipfile; zipfile.ZipFile(r'$WHL_WIN').namelist()" 2>/dev/null; then
    echo "wheel intact"
  else
    echo "wheel missing/corrupt after retries"; exit 1
  fi
  echo "--- pip install torch ---"
  "$PY" -m pip install --upgrade pip setuptools wheel
  "$PY" -m pip install "$WHL_WIN"
  "$PY" -c "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available(),(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no-cuda'))"
  echo "=== $(date) PARALLEL torch install DONE verify_rc=$? ==="
  # clean the parts to reclaim space
  rm -rf "$RUN/wheels/parts" 2>/dev/null || true
} >> "$LOG" 2>&1
