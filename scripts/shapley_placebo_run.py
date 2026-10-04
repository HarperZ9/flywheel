"""shapley_placebo_run.py -- run the Shapley placebo test against a local Ollama model.

Starts its own `ollama serve` on a free loopback port (never the default 11434),
evaluates every coalition of every item with greedy decoding, stops the server
and every process it started by PID, and writes the full record: coalition
outputs and values, exact Shapley values, trials, and the analysis. With
--gpu-lock it holds a directory lock (scripts/gpu_lock.py) for the whole run.

    python scripts/shapley_placebo_run.py --items items-v1.json --out run.json \\
        --model qwen2.5:7b [--models-dir DIR] [--gpu-lock DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from harness import shapley_far as sf  # noqa: E402
import gpu_lock  # noqa: E402

OPTIONS = {"temperature": 0, "seed": 0, "num_predict": 24, "num_ctx": 4096}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(url: str, body: dict | None = None, timeout: float = 120) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _start_server(exe: str, models_dir: str | None, port: int):
    env = dict(os.environ, OLLAMA_HOST=f"127.0.0.1:{port}")
    if models_dir:
        env["OLLAMA_MODELS"] = models_dir
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen([exe, "serve"], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=flags)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            _http(base + "/api/version", timeout=2)
            return proc, base
        except OSError:
            time.sleep(0.5)
    _stop_server(proc)
    raise RuntimeError("ollama serve did not answer within 60 s")


def _children(pid: int) -> list:
    if platform.system() != "Windows":
        out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
        return [int(x) for x in out.split()]
    cmd = (f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' "
           "| ForEach-Object { $_.ProcessId }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                         capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def _stop_server(proc) -> list:
    """Kill the server and its runner children by PID. Returns PIDs still alive."""
    pids = [proc.pid] + _children(proc.pid)
    for pid in pids:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True)
    proc.wait(timeout=30)
    time.sleep(1)
    alive = []
    for pid in pids:
        probe = (["tasklist", "/FI", f"PID eq {pid}", "/NH"] if platform.system() == "Windows"
                 else ["ps", "-p", str(pid)])
        if str(pid) in subprocess.run(probe, capture_output=True, text=True).stdout:
            alive.append(pid)
    return alive


def _run_item(base: str, model: str, item: dict) -> dict:
    n, outputs, values = len(item["sources"]), [], []
    t0 = time.perf_counter()
    for mask in range(1 << n):
        r = _http(base + "/api/generate", {"model": model, "stream": False, "options": OPTIONS,
                                           "prompt": sf.prompt(item["question"], item["sources"], mask)})
        outputs.append(r["response"])
        values.append(sf.answer_value(r["response"], item["accepted"]))
    return {"item_id": item["item_id"], "calls": 1 << n, "seconds": round(time.perf_counter() - t0, 3),
            "outputs": outputs, "values": values}


def _model_digest(base: str, model: str) -> str | None:
    for m in _http(base + "/api/tags").get("models", []):
        if m.get("name") == model or m.get("name") == model + ":latest":
            return m.get("digest")
    return None


def _evaluate(a, items: dict, base: str) -> dict:
    runs = [_run_item(base, a.model, it) for it in items["items"]]
    trials = [t for it, run in zip(items["items"], runs) for t in sf.item_trials(it, run["values"])]
    witness = [{"path": "items-v1.json", "sha256": hashlib.sha256(Path(a.items).read_bytes()).hexdigest()},
               {"path": "harness/shapley_far.py",
                "sha256": hashlib.sha256((ROOT / "harness/shapley_far.py").read_bytes()).hexdigest()}]
    env = sf.manifest(f"shapley-placebo/{a.model}", witness)
    return {"runs": runs, "trials": trials, "analysis": sf.analyze(trials, env),
            "witness": witness, "model_digest": _model_digest(base, a.model),
            "ollama_version": _http(base + "/api/version").get("version")}


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--items", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default="qwen2.5:7b")
    p.add_argument("--ollama", default=shutil.which("ollama") or "ollama")
    p.add_argument("--models-dir")
    p.add_argument("--gpu-lock")
    a = p.parse_args(argv)
    items = json.loads(Path(a.items).read_text(encoding="utf-8"))
    token = gpu_lock.acquire(a.gpu_lock, "shapley placebo test", "flywheel") if a.gpu_lock else None
    proc = None
    try:
        port = _free_port()
        proc, base = _start_server(a.ollama, a.models_dir, port)
        t0 = time.perf_counter()
        record = _evaluate(a, items, base)
        record.update(model=a.model, options=OPTIONS, port=port, scoring_rule=sf.SCORING_RULE,
                      prompt_rule=sf.PROMPT_RULE, wall_seconds=round(time.perf_counter() - t0, 1),
                      items_sha256=record["witness"][0]["sha256"])
    finally:
        alive = _stop_server(proc) if proc else []
        if token:
            gpu_lock.release(a.gpu_lock, token)
    record["server_pids_alive_after_stop"] = alive
    Path(a.out).write_text(json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps(record["analysis"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
