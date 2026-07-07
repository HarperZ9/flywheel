#!/usr/bin/env bash
export PATH="$HOME/venv-lm/bin:$PATH"
for i in $(seq 1 50); do curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1 && break; sleep 6; done
if ! curl -sf http://127.0.0.1:8765/health >/dev/null 2>&1; then echo "serve not up"; tail -3 /mnt/e/local-model-run/logs/serve-ablation.log; exit 1; fi
echo "serve up; running ablation..."
cd /mnt/c/dev/local-model
PYTHONPATH=/mnt/c/dev/local-model "$HOME/venv-lm/bin/python" scripts/run_ablation.py http://127.0.0.1:8765
