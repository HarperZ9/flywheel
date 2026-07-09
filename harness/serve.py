#!/usr/bin/env python3
"""
serve.py - Layer B M0: deterministic proposer (HARNESS-ROADMAP.md M0).

Serves the local model over a small HTTP endpoint. M0's falsifier: a fixed
prompt + fixed seed reproduces the same output. Returns
{text, seed, model_ref, prompt_hash, cache}.

Proposer-agnostic: set ADAPTER_PATH for a trained LoRA adapter, or repoint
MODEL_PATH to the 32B. M1-M7 are unchanged by the proposer.

Prefix caching: M0 ships determinism + an exact (prompt_hash, seed, params)
result memo (cache field = "exact" on hit). True prefix-KV caching
(RadixAttention: reuse prefill KV across same-prefix/different-suffix) is M5 and
needs a serving backend (vLLM/SGLang) - likely WSL2 on this box. See
HARNESS-ROADMAP.md M0/M5.
"""
from __future__ import annotations
import hashlib
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("HF_HOME", r"E:\local-model-run\hf-cache")
os.environ.setdefault("PIP_CACHE_DIR", r"E:\local-model-run\pip-cache")
os.environ.setdefault("TMP", r"E:\local-model-run\tmp")
os.environ.setdefault("TEMP", r"E:\local-model-run\tmp")
os.environ.setdefault("BITSANDBYTES_NOWELCOME", "1")

try:
    from .messages_api import error_response, resolve_model, translate_request, translate_response
except ImportError:  # pragma: no cover - supports `python harness/serve.py`
    from messages_api import error_response, resolve_model, translate_request, translate_response

torch = None

# Env-overridable so the SAME server runs on Windows (E:\...) or in WSL
# (/mnt/e/...) — the working GPU stack is WSL, so the endgame sets these to
# Linux paths without editing this file.
MODEL_PATH = os.environ.get(
    "SERVE_MODEL_PATH", r"E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct")
ADAPTER_PATH = os.environ.get("SERVE_ADAPTER_PATH", "")  # trained LoRA adapter dir
MODEL_REF = "Qwen2.5-Coder-14B-Instruct (base, nf4)"
PORT = int(os.environ.get("SERVE_PORT", "8765"))
QUANT_4BIT = True
SERVE_DEVICE_MAP = os.environ.get("SERVE_DEVICE_MAP", "cuda").strip().lower()
SERVE_MAX_MEMORY_GPU = os.environ.get("SERVE_MAX_MEMORY_GPU", "").strip()
SERVE_MAX_MEMORY_CPU = os.environ.get("SERVE_MAX_MEMORY_CPU", "").strip()
SERVE_OFFLOAD_FOLDER = os.environ.get("SERVE_OFFLOAD_FOLDER", "").strip()
MODEL_CATALOG = {
    "14b": {
        "path": r"E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct",
        "ref": "Qwen2.5-Coder-14B-Instruct (base, nf4)",
        "aliases": ("14b", "14b-base", "qwen2.5-coder-14b"),
    },
    "32b": {
        "path": r"E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct",
        "ref": "Qwen2.5-Coder-32B-Instruct (base, nf4)",
        "aliases": ("32b", "32b-base", "qwen2.5-coder-32b"),
    },
}


def _resolve_model_path() -> tuple[str, str]:
    """Resolve model path/ref from env overrides and optional aliases."""
    alias = os.environ.get("SERVE_MODEL_ALIAS", "").strip().lower()
    model_path = os.environ.get("SERVE_MODEL_PATH", "").strip()
    model_ref = os.environ.get("SERVE_MODEL_REF", "").strip()

    if not model_path and alias:
        for spec in MODEL_CATALOG.values():
            if alias == spec["aliases"][0] or alias in spec["aliases"]:
                model_path = spec["path"]
                if not model_ref:
                    model_ref = spec["ref"]
                return model_path, model_ref or spec["ref"]

    if not model_path:
        default_spec = MODEL_CATALOG["14b"]
        if alias:
            for spec in MODEL_CATALOG.values():
                if alias == spec["aliases"][0] or alias in spec["aliases"]:
                    model_path = spec["path"]
                    if not model_ref:
                        model_ref = spec["ref"]
                    break
        if not model_path:
            model_path = default_spec["path"]
        model_ref = model_ref or default_spec["ref"]

    return model_path, model_ref or os.path.basename(model_path)


def apply_model_profile(model_profile: str = "", model_path: str = "",
                       model_ref: str = "") -> tuple[str, str]:
    """
    Apply explicit CLI/env overrides before the model is loaded.
    """
    profile = model_profile.strip().lower() or os.environ.get("SERVE_MODEL_ALIAS", "").strip().lower()
    explicit_path = model_path.strip() or os.environ.get("SERVE_MODEL_PATH", "").strip()
    explicit_ref = model_ref.strip() or os.environ.get("SERVE_MODEL_REF", "").strip()

    if explicit_path:
        resolved_path = explicit_path
        resolved_ref = explicit_ref or os.path.basename(explicit_path)
        if profile and profile in {"14b", "14b-base", "32b", "32b-base", "qwen2.5-coder-14b", "qwen2.5-coder-32b"}:
            for spec in MODEL_CATALOG.values():
                if profile == spec["aliases"][0] or profile in spec["aliases"]:
                    resolved_ref = explicit_ref or spec["ref"]
                    break
        return resolved_path, resolved_ref

    for spec in MODEL_CATALOG.values():
        if profile == spec["aliases"][0] or profile in spec["aliases"]:
            return spec["path"], explicit_ref or spec["ref"]

    if not profile:
        return _resolve_model_path()

    env_path = MODEL_CATALOG.get(profile, {}).get("path") if profile in MODEL_CATALOG else ""
    if env_path:
        return env_path, explicit_ref or MODEL_CATALOG[profile]["ref"]

    default_spec = MODEL_CATALOG["14b"]
    return default_spec["path"], explicit_ref or default_spec["ref"]

_tok = None
_model = None
_lock = threading.Lock()
_memo: dict[tuple, str] = {}


def _torch():
    global torch
    if torch is None:
        import torch as torch_mod
        torch = torch_mod
    return torch


def _device_map_config():
    if SERVE_DEVICE_MAP in {"cuda", "gpu", "single-gpu"}:
        return {"": 0}, {}
    if SERVE_DEVICE_MAP == "auto":
        max_memory = {}
        if SERVE_MAX_MEMORY_GPU:
            max_memory[0] = SERVE_MAX_MEMORY_GPU
        if SERVE_MAX_MEMORY_CPU:
            max_memory["cpu"] = SERVE_MAX_MEMORY_CPU
        extra = {}
        if max_memory:
            extra["max_memory"] = max_memory
        if SERVE_OFFLOAD_FOLDER:
            Path(SERVE_OFFLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
            extra["offload_folder"] = SERVE_OFFLOAD_FOLDER
        return "auto", extra
    if SERVE_DEVICE_MAP == "cpu":
        return {"": "cpu"}, {}
    return {"": 0}, {}


def load() -> None:
    global _tok, _model
    torch_mod = _torch()
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    kw = dict(torch_dtype=torch_mod.bfloat16)
    if QUANT_4BIT:
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch_mod.bfloat16,
        )
    device_map, dispatch_kw = _device_map_config()
    kw.update(dispatch_kw)
    _tok = AutoTokenizer.from_pretrained(MODEL_PATH)
    _model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, device_map=device_map, **kw)
    if ADAPTER_PATH:
        from peft import PeftModel
        _model = PeftModel.from_pretrained(_model, ADAPTER_PATH)
        global MODEL_REF
        MODEL_REF = f"{MODEL_REF} + adapter {os.path.basename(ADAPTER_PATH)}"
    _model.eval()
    _model.config.use_cache = True


def _render(prompt: str, system: str = "") -> str:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return _tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def generate(prompt: str, max_new_tokens: int = 128, temperature: float = 0.0,
             top_p: float = 0.9, seed: int = 0, system: str = "") -> dict:
    torch_mod = _torch()
    text = _render(prompt, system)
    ph = hashlib.sha256(text.encode()).hexdigest()[:16]
    do_sample = float(temperature) > 0.0
    key = (ph, int(max_new_tokens), int(seed), float(temperature), float(top_p))
    cached = _memo.get(key)
    if cached is not None:
        return _wrap(cached, ph, seed, "exact")
    with _lock:
        if do_sample:
            torch_mod.manual_seed(seed)
            if torch_mod.cuda.is_available():
                torch_mod.cuda.manual_seed_all(seed)
        if torch_mod.cuda.is_available():
            torch_mod.cuda.empty_cache()
        ids = _tok(text, return_tensors="pt").to(_model.device)
        with torch_mod.no_grad():
            out = _model.generate(
                **ids,
                max_new_tokens=int(max_new_tokens),
                do_sample=do_sample,
                temperature=float(temperature) if do_sample else 1.0,
                top_p=float(top_p),
                pad_token_id=_tok.eos_token_id,
            )
        new = out[0][ids["input_ids"].shape[1]:]
        txt = _tok.decode(new, skip_special_tokens=True)
    _memo[key] = txt
    return _wrap(txt, ph, seed, "miss")


def _wrap(txt: str, ph: str, seed: int, cache: str) -> dict:
    return {"text": txt, "seed": seed, "model_ref": MODEL_REF,
            "prompt_hash": ph, "cache": cache}


class _H(BaseHTTPRequestHandler):
    def _extract_chat_prompt(self, req: dict) -> str:
        messages = req.get("messages", [])
        system = ""
        parts = []
        for msg in messages if isinstance(messages, list) else []:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "system" and not system:
                system = msg.get("content", "")
            if "content" in msg:
                role = str(msg.get("role", "user"))
                parts.append(f"{role}: {msg.get('content', '')}")
        return system, "\n".join(parts)

    def log_message(self, *a):
        pass

    def _send(self, code: int, obj: dict, headers: dict | None = None) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            if value is not None:
                self.send_header(key, str(value))
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        if self.path not in ("/generate", "/chat/completions", "/v1/messages"):
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or "{}")
            if self.path == "/v1/messages":
                try:
                    params = translate_request(req)
                except ValueError as e:
                    self._send(400, error_response(str(e)))
                    return
                served_ref = resolve_model(params.get("requested_model", ""), MODEL_REF)
                payload = generate(
                    params["prompt"],
                    int(params.get("max_new_tokens", 512)),
                    float(params.get("temperature", 0.0)),
                    float(req.get("top_p", 0.9)),
                    int(params.get("seed", 0)),
                    params.get("system", ""),
                )
                reply = translate_response(payload, params, served_ref)
                receipt_id = reply.get("x_receipt", {}).get("receipt_id")
                self._send(200, reply, {"X-Receipt-Id": receipt_id})
            elif self.path == "/chat/completions":
                system, prompt = self._extract_chat_prompt(req)
                max_new_tokens = int(req.get("max_tokens", 128))
                req_system = req.get("system", "")
                temperature = float(req.get("temperature", 0.0))
                top_p = float(req.get("top_p", 0.9))
                seed = int(req.get("seed", 0))
                payload = generate(
                    prompt,
                    max_new_tokens,
                    temperature,
                    top_p,
                    seed,
                    req_system or system,
                )
                reply = {
                    "id": "chatcmpl-local",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": payload["model_ref"],
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": payload["text"]},
                            "finish_reason": "stop",
                        },
                    ],
                    "usage": {},
                }
                self._send(200, reply)
            else:
                r = generate(
                    req["prompt"],
                    int(req.get("max_new_tokens", 128)),
                    float(req.get("temperature", 0.0)),
                    float(req.get("top_p", 0.9)),
                    int(req.get("seed", 0)),
                    req.get("system", ""),
                )
                self._send(200, r)
        except Exception as e:
            self._send(500, error_response(repr(e), etype="api_error"))

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {
                "ok": True,
                "model_path": MODEL_PATH,
                "model_ref": MODEL_REF,
            })
        else:
            self._send(404, {"error": "not found"})


def main(argv: list[str] | None = None) -> int:
    global MODEL_PATH, MODEL_REF, PORT, SERVE_DEVICE_MAP, SERVE_MAX_MEMORY_GPU, SERVE_MAX_MEMORY_CPU, SERVE_OFFLOAD_FOLDER
    ap = argparse.ArgumentParser(description="local harness serve executable")
    ap.add_argument("--model-profile", default=os.environ.get("SERVE_MODEL_ALIAS", "14b"),
                    help="14b | 32b | custom")
    ap.add_argument("--model-path", default="",
                    help="explicit local path for the model directory (overrides profile)")
    ap.add_argument("--model-ref", default=os.environ.get("SERVE_MODEL_REF", ""),
                    help="override receipt model_ref string")
    ap.add_argument("--port", default=str(PORT), type=int, help="listen port")
    ap.add_argument("--device-map", default=SERVE_DEVICE_MAP,
                    help="cuda | auto | cpu; auto enables max-memory/offload options")
    ap.add_argument("--max-memory-gpu", default=SERVE_MAX_MEMORY_GPU,
                    help="GPU memory cap for transformers auto device_map, e.g. 20GiB")
    ap.add_argument("--max-memory-cpu", default=SERVE_MAX_MEMORY_CPU,
                    help="CPU memory cap for transformers auto device_map, e.g. 48GiB")
    ap.add_argument("--offload-folder", default=SERVE_OFFLOAD_FOLDER,
                    help="folder for accelerate/transformers offload state")
    args = ap.parse_args(argv)

    MODEL_PATH, MODEL_REF = apply_model_profile(args.model_profile, args.model_path, args.model_ref)
    PORT = args.port
    SERVE_DEVICE_MAP = args.device_map.strip().lower()
    SERVE_MAX_MEMORY_GPU = args.max_memory_gpu.strip()
    SERVE_MAX_MEMORY_CPU = args.max_memory_cpu.strip()
    SERVE_OFFLOAD_FOLDER = args.offload_folder.strip()

    load()
    print(f"[serve] {MODEL_REF} device_map={SERVE_DEVICE_MAP} listening on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), _H).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
