#!/usr/bin/env bash
# wsl_vllm_spike.sh — Phase C of the vLLM/WSL2 spike. RUNS INSIDE WSL2.
# De-risks M5: (1) GPU visible from WSL2, (2) vLLM serves the 14B in 4-bit,
# (3) prefix caching actually hits, (4) seed determinism holds.
# Idempotent. Logs to /mnt/e/local-model-run/logs/vllm-spike.log.
set -euo pipefail

MODEL="/mnt/e/local-model-run/models/Qwen2.5-Coder-14B-Instruct"
VENV="$HOME/vllm-spike-venv"
PORT="${SERVE_PORT:-8765}"
SERVED="qwen14b"                       # --served-model-name (stable client ref)
LOG="/mnt/e/local-model-run/logs/vllm-spike.log"

echo "==== [1/5] preflight: GPU visible from WSL2? ===="
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "FAIL: nvidia-smi not found in WSL2 — Windows NVIDIA driver not exposing the GPU."
  echo "      Fix: ensure Windows NVIDIA driver (>=470) is installed; WSL uses the Windows driver, no Linux driver needed."
  exit 1
fi
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
[ -f "$MODEL/config.json" ] || { echo "FAIL: model not at $MODEL (is E: mounted at /mnt/e?)"; exit 1; }
mkdir -p "$(dirname "$LOG")"

echo "==== [2/5] python + venv ===="
if ! command -v python3 >/dev/null 2>&1; then
  sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
fi
python3 --version
[ -d "$VENV" ] || python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --quiet --upgrade pip

echo "==== [3/5] install vLLM (Linux path — clean; pulls torch cu12). ~5-15 min first time. ===="
pip install --quiet vllm
python -c "import vllm; print('vllm', vllm.__version__)"
python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no-gpu')"

echo "==== [4/5] serve 14B, 4-bit (bitsandbytes), prefix caching ON (background) ===="
# NOTE: loading 27GB bf16 via /mnt/e (drvfs) is slow first time (~10-15 min).
# Production fix: copy the model into the WSL ext4 filesystem for fast loads.
vllm serve "$MODEL" \
  --served-model-name "$SERVED" \
  --quantization bitsandbytes \
  --dtype bfloat16 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.85 \
  --enable-prefix-caching \
  --enforce-eager \
  --port "$PORT" --host 127.0.0.1 \
  > "$LOG" 2>&1 &
VLLM_PID=$!
echo "vLLM PID=$VLLM_PID -> $LOG"
echo "waiting for /health (cap 25 min for slow drvfs load)..."
UP=0
for i in $(seq 1 150); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then UP=1; echo "vLLM UP after ~$((i*10))s"; break; fi
  if ! kill -0 "$VLLM_PID" 2>/dev/null; then echo "FAIL: vLLM process died. Last log:"; tail -40 "$LOG"; exit 1; fi
  sleep 10
done
[ "$UP" = 1 ] || { echo "FAIL: vLLM not healthy in 25 min. Last log:"; tail -40 "$LOG"; exit 1; }

echo "==== [5/5] determinism + prefix-cache probe (stdlib only) ===="
python - <<PYEOF
import json, urllib.request, time
BASE="http://127.0.0.1:$PORT"
def comp(prompt, max_tokens, temperature, seed):
    body=json.dumps({"model":"$SERVED","prompt":prompt,"max_tokens":max_tokens,
                     "temperature":temperature,"seed":seed}).encode()
    req=urllib.request.Request(BASE+"/v1/completions", data=body,
                               headers={"Content-Type":"application/json"})
    t0=time.time()
    r=json.loads(urllib.request.urlopen(req, timeout=120).read())
    r["_wall"]=time.time()-t0
    return r
SYS=("You are a precise Python code assistant. Use only the standard library. "
     "Reply with a single complete function and nothing else. "
     "This long shared system preamble is intentionally verbose to make the "
     "prefix-cache signal unmistakable across requests. " * 6)
P1=SYS+"\n\nUser: Write a function fib(n) returning the n-th Fibonacci number.\nAssistant:"
P2=SYS+"\n\nUser: Write a function factorial(n).\nAssistant:"
# warm the prefix with P1
a=comp(P1, 20, 0.7, 42)
# determinism: same P1 + seed, +1 token -> shared prefix must match
b=comp(P1, 21, 0.7, 42)
ta=a["choices"][0]["text"]; tb=b["choices"][0]["text"]
print("DETERMINISM (seeded): A is prefix of B?", tb.startswith(ta))
print("  A:", repr(ta)); print("  B:", repr(tb))
# prefix-cache signal: P2 shares the long SYS prefix with P1 -> 2nd distinct request faster prefill
cold=comp(P2, 10, 0.0, 0)
hot =comp(P2, 10, 0.0, 0)   # identical -> memoized/fully cached
print(f"PREFIX-CACHE wall: P2 cold={cold['_wall']:.3f}s  P2-hot(repeat)={hot['_wall']:.3f}s  (hot should be much faster)")
print("  (vLLM also logs 'cache hit' metrics in the server log; grep there for the authoritative number.)")
PYEOF

echo "==== prefix-cache metrics from server log ===="
grep -iE 'cache|prefix' "$LOG" | tail -20 || echo "(no cache lines in log yet)"

echo "==== SPIKE DONE ===="
echo "vLLM still running on 127.0.0.1:$PORT (kill: kill $VLLM_PID in WSL)."
echo "Reachable from Windows at http://127.0.0.1:$PORT (WSL2 localhost forwarding on Win11)."
echo "Verdict: if DETERMINISM=True and P2-hot << P2-cold, M5 is de-risked (real prefix caching works)."
