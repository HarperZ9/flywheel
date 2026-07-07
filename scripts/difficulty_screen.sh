#!/usr/bin/env bash
# difficulty_screen.sh — serve the trained 14B adapter and run the single-shot
# difficulty screen over the curated hard-set registry (run inside WSL2).
# Same idioms as finish_and_eval.sh: latest checkpoint w/ drvfs retry, venv on
# PATH for the pytest oracle, health-gated serve, cleanup on exit.
set -uo pipefail

RUN=/mnt/e/local-model-run
PY="$HOME/venv-lm/bin/python"
SRC=/mnt/c/dev/local-model
PORT="${SERVE_PORT:-8765}"

CKPT_DIR="$RUN/checkpoints/phase2-linux-qlora-cpt-14b"
ADAPTER=""
for try in 1 2 3 4 5; do
  ADAPTER=$(ls -d "$CKPT_DIR"/checkpoint-* 2>/dev/null | sed 's#.*checkpoint-##' | sort -n | tail -1)
  [ -n "$ADAPTER" ] && break
  echo "checkpoint listing empty (drvfs hiccup?) — retry $try/5"; sleep 3
done
[ -z "$ADAPTER" ] && { echo "no checkpoint in $CKPT_DIR after retries"; exit 2; }
echo "=== difficulty screen: serving adapter checkpoint-$ADAPTER ==="

"$PY" -c "import pytest" 2>/dev/null || "$PY" -m pip install -q pytest
export PATH="$HOME/venv-lm/bin:$PATH"

export SERVE_MODEL_PATH="$RUN/models/Qwen2.5-Coder-14B-Instruct"
export SERVE_ADAPTER_PATH="$CKPT_DIR/checkpoint-$ADAPTER"
export SERVE_PORT="$PORT"
export PYTHONPATH="$SRC"
export HF_HOME="$RUN/hf-cache"
export HF_HUB_OFFLINE=1
export BITSANDBYTES_NOWELCOME=1
export TOKENIZERS_PARALLELISM=false

mkdir -p "$RUN/logs"
"$PY" "$SRC/harness/serve.py" >> "$RUN/logs/serve-screen.log" 2>&1 &
SERVE_PID=$!
trap 'kill $SERVE_PID 2>/dev/null' EXIT

echo "waiting for /health (model load ~2-4 min)..."
up=0
for i in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then up=1; echo "serve up after $((i*5))s"; break; fi
  sleep 5
done
[ "$up" = "0" ] && { echo "serve did not come up; tail serve-screen.log:"; tail -20 "$RUN/logs/serve-screen.log"; exit 3; }

echo "=== screening curated registry (single_shot@temp0) ==="
"$PY" "$SRC/scripts/difficulty_screen.py" --serve "http://127.0.0.1:$PORT" \
  --workroot "$HOME/.screen-run" \
  --out "$RUN/difficulty_screen_v2.json"
rc=$?
cp -f "$RUN/difficulty_screen_v2.json" "$SRC/tasks/research/difficulty_screen_v2.json" 2>/dev/null
echo "=== screen done rc=$rc -> $RUN/difficulty_screen_v2.json (+ repo copy) ==="
exit $rc
