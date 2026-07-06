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
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("HF_HOME", r"E:\local-model-run\hf-cache")
os.environ.setdefault("PIP_CACHE_DIR", r"E:\local-model-run\pip-cache")
os.environ.setdefault("TMP", r"E:\local-model-run\tmp")
os.environ.setdefault("TEMP", r"E:\local-model-run\tmp")
os.environ.setdefault("BITSANDBYTES_NOWELCOME", "1")

import torch

MODEL_PATH = r"E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct"
ADAPTER_PATH = ""  # set to a trained LoRA adapter dir to serve the adapted model
MODEL_REF = "Qwen2.5-Coder-14B-Instruct (base, nf4)"
PORT = int(os.environ.get("SERVE_PORT", "8765"))
QUANT_4BIT = True

_tok = None
_model = None
_lock = threading.Lock()
_memo: dict[tuple, str] = {}


def load() -> None:
    global _tok, _model
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    kw = dict(torch_dtype=torch.bfloat16)
    if QUANT_4BIT:
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
    _tok = AutoTokenizer.from_pretrained(MODEL_PATH)
    _model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, device_map={"": 0}, **kw)
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
    text = _render(prompt, system)
    ph = hashlib.sha256(text.encode()).hexdigest()[:16]
    do_sample = float(temperature) > 0.0
    key = (ph, int(max_new_tokens), int(seed), float(temperature), float(top_p))
    cached = _memo.get(key)
    if cached is not None:
        return _wrap(cached, ph, seed, "exact")
    with _lock:
        if do_sample:
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        ids = _tok(text, return_tensors="pt").to(_model.device)
        with torch.no_grad():
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
    def log_message(self, *a):
        pass

    def _send(self, code: int, obj: dict) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        if self.path != "/generate":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or "{}")
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
            self._send(500, {"error": repr(e)})

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "model_ref": MODEL_REF})
        else:
            self._send(404, {"error": "not found"})


def main() -> int:
    load()
    print(f"[serve] {MODEL_REF} listening on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), _H).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
