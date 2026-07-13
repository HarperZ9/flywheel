#!/usr/bin/env bash
# Autonomously finish Phase 0 -> 1 across the I/O waits:
#   wait for torch  ->  install rest of stack  ->  tokenize + pack the corpus.
# Tokenization needs only the tokenizer files (already downloaded), so Phase 1
# can complete while the 28 GB of weights are still downloading in parallel.
set -uo pipefail
RUN=/e/local-model-run
PY="$RUN/venv/Scripts/python.exe"
MODEL_MSYS=/e/local-model-run/models/Qwen2.5-Coder-14B-Instruct
export HF_HOME='E:\local-model-run\hf-cache'
export PIP_CACHE_DIR='E:\local-model-run\pip-cache'
export TMP='E:\local-model-run\tmp'; export TEMP='E:\local-model-run\tmp'
export BITSANDBYTES_NOWELCOME=1
mkdir -p "$RUN/tmp" "$RUN/logs"
LOG="$RUN/logs/chain-phase01.log"
{
  echo "=== $(date) chain phase0->1 START ==="

  echo "--- waiting for torch to become importable (max ~60m) ---"
  ok=0
  for i in $(seq 1 240); do
    if "$PY" -c "import torch" 2>/dev/null; then ok=1; echo "torch ready (~$((i*15))s)"; break; fi
    sleep 15
  done
  [ "$ok" = "1" ] || { echo "TIMEOUT waiting for torch; abort"; exit 1; }

  echo "--- installing rest of the training stack ---"
  bash /c/dev/local-model/scripts/install_rest.sh
  if ! "$PY" -c "import transformers,peft,trl,accelerate,datasets,bitsandbytes,safetensors,sentencepiece; print('stack import ok')"; then
    echo "stack import FAILED; abort"; exit 2
  fi

  echo "--- waiting for tokenizer files (max ~20m) ---"
  for i in $(seq 1 120); do
    [ -f "$MODEL_MSYS/tokenizer.json" ] && [ -f "$MODEL_MSYS/tokenizer_config.json" ] && { echo "tokenizer present"; break; }
    sleep 10
  done

  echo "--- tokenize + pack corpus ---"
  "$PY" "C:/dev/local-model/dataset/tokenize_pack.py"
  rc=$?
  echo "=== $(date) chain phase0->1 DONE tokenize_rc=$rc ==="
} >> "$LOG" 2>&1
