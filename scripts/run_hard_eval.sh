#!/usr/bin/env bash
# Wait for the served model, then run M7 on the HARDER held-out set.
export PATH="$HOME/venv-lm/bin:$PATH"
"$HOME/venv-lm/bin/python" -c "import pytest" 2>/dev/null || "$HOME/venv-lm/bin/python" -m pip install -q pytest
echo "waiting for /health..."
up=0
for i in $(seq 1 50); do
  if curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then up=1; echo "serve up after $((i*6))s"; break; fi
  sleep 6
done
[ "$up" = "0" ] && { echo "serve not up; tail serve-hard.log:"; tail -8 /mnt/e/local-model-run/logs/serve-hard.log; exit 3; }
cd /mnt/c/dev/local-model
PYTHONPATH=/mnt/c/dev/local-model "$HOME/venv-lm/bin/python" scripts/run_m7_eval.py \
  --hard --serve http://127.0.0.1:8765 \
  --out /mnt/e/local-model-run/m7_hard_scorecard.json \
  --workroot /mnt/e/local-model-run/tmp/m7hard
