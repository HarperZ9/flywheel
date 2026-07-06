#!/usr/bin/env bash
# finish_and_eval.sh — the GPU endgame, one command (run inside WSL2 Ubuntu).
# After the 14B CPT completes: serve the trained LoRA adapter and run the M7 eval
# (harness lift: verified_inference vs single_shot of the same model). Idempotent;
# picks the latest checkpoint. serve.py MODEL/ADAPTER paths are env-overridable.
set -uo pipefail

RUN=/mnt/e/local-model-run
PY="$HOME/venv-lm/bin/python"
SRC=/mnt/c/dev/local-model
PORT="${SERVE_PORT:-8765}"

CKPT_DIR="$RUN/checkpoints/phase2-linux-qlora-cpt-14b"
# drvfs 9p over /mnt/e can transiently return an EMPTY listing under GPU load;
# retry before concluding there is no checkpoint.
ADAPTER=""
for try in 1 2 3 4 5; do
  ADAPTER=$(ls -d "$CKPT_DIR"/checkpoint-* 2>/dev/null | sed 's#.*checkpoint-##' | sort -n | tail -1)
  [ -n "$ADAPTER" ] && break
  echo "checkpoint listing empty (drvfs hiccup?) — retry $try/5"; sleep 3
done
[ -z "$ADAPTER" ] && { echo "no checkpoint in $CKPT_DIR after retries"; exit 2; }
ADAPTER_DIR="$CKPT_DIR/checkpoint-$ADAPTER"
echo "=== M7 endgame: serving adapter checkpoint-$ADAPTER ==="

# The oracle runs `python -m pytest`; put the venv on PATH so `python` resolves
# to it (WSL has only python3), and ensure pytest is present (training venv omits
# it). run_env() inherits os.environ, so the oracle subprocess gets this PATH.
"$PY" -c "import pytest" 2>/dev/null || "$PY" -m pip install -q pytest
export PATH="$HOME/venv-lm/bin:$PATH"

export SERVE_MODEL_PATH="$RUN/models/Qwen2.5-Coder-14B-Instruct"
export SERVE_ADAPTER_PATH="$ADAPTER_DIR"
export SERVE_PORT="$PORT"
export PYTHONPATH="$SRC"
export HF_HOME="$RUN/hf-cache"
export HF_HUB_OFFLINE=1
export BITSANDBYTES_NOWELCOME=1
export TOKENIZERS_PARALLELISM=false

mkdir -p "$RUN/logs"
"$PY" "$SRC/harness/serve.py" >> "$RUN/logs/serve-m7.log" 2>&1 &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null' EXIT

echo "waiting for /health (model load ~2-4 min)..."
up=0
for i in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then up=1; echo "serve up after $((i*5))s"; break; fi
  sleep 5
done
[ "$up" = "0" ] && { echo "serve did not come up; tail serve-m7.log:"; tail -20 "$RUN/logs/serve-m7.log"; exit 3; }

echo "=== running M7 eval ==="
"$PY" "$SRC/scripts/run_m7_eval.py" --serve "http://127.0.0.1:$PORT" \
  --out "$RUN/m7_scorecard.json"
rc=$?
echo "=== M7 done rc=$rc; scorecard at $RUN/m7_scorecard.json ==="
exit $rc
