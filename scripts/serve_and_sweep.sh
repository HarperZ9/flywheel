#!/usr/bin/env bash
# serve_and_sweep.sh — serve the trained 14B and run the encoding sweep
# (labels vs reasoning vs raw) to diagnose the COPY-ONLY finding. Run in WSL2.
set -uo pipefail

RUN=/mnt/e/local-model-run
PY="$HOME/venv-lm/bin/python"
SRC=/mnt/c/dev/local-model
CKPT="$RUN/checkpoints/phase2-linux-qlora-cpt-14b/checkpoint-2020"

"$PY" -c "import pytest" 2>/dev/null || "$PY" -m pip install -q pytest
export PATH="$HOME/venv-lm/bin:$PATH"
export SERVE_MODEL_PATH="$RUN/models/Qwen2.5-Coder-14B-Instruct"
export SERVE_ADAPTER_PATH="$CKPT"
export PYTHONPATH="$SRC"
export HF_HOME="$RUN/hf-cache" HF_HUB_OFFLINE=1 BITSANDBYTES_NOWELCOME=1 TOKENIZERS_PARALLELISM=false

pkill -f "harness/serve.py" 2>/dev/null; sleep 2
mkdir -p "$RUN/logs"
"$PY" "$SRC/harness/serve.py" >> "$RUN/logs/serve-sweep.log" 2>&1 &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null' EXIT

echo "waiting for /health..."
up=0
for i in $(seq 1 90); do
  if curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then up=1; echo "serve up after $((i*5))s"; break; fi
  sleep 5
done
[ "$up" = "0" ] && { echo "serve did not come up"; tail -12 "$RUN/logs/serve-sweep.log"; exit 3; }

echo "=== encoding sweep (labels vs reasoning vs raw) ==="
"$PY" "$SRC/scripts/run_encoding_sweep.py" --serve http://127.0.0.1:8765 --n 20 \
  --out "$RUN/encoding_sweep_scorecard.json"
rc=$?
echo "=== sweep done rc=$rc ==="
exit $rc
