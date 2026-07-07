#!/usr/bin/env bash
# serve_and_probe.sh — serve the trained 14B and run the behavioral perception
# measurement (conserving vs naive encoding locate accuracy). Run inside WSL2.
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

mkdir -p "$RUN/logs"
"$PY" "$SRC/harness/serve.py" >> "$RUN/logs/serve-perc.log" 2>&1 &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null' EXIT

echo "waiting for /health (model load ~2-3 min)..."
up=0
for i in $(seq 1 90); do
  if curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then up=1; echo "serve up after $((i*5))s"; break; fi
  sleep 5
done
[ "$up" = "0" ] && { echo "serve did not come up"; tail -15 "$RUN/logs/serve-perc.log"; exit 3; }

echo "=== perception probe (conserving vs naive locate accuracy) ==="
"$PY" "$SRC/scripts/run_perception_probe.py" --serve http://127.0.0.1:8765 --n 20 \
  --out "$RUN/perception_scorecard.json"
rc=$?
echo "=== perception probe done rc=$rc ==="
exit $rc
