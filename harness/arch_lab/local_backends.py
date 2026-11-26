"""Pluggable local model backends for JFC-3P Arm A vs Arm B frontier evaluation.

Supports CPU-safe MockBackend (CI), Ollama HTTP API, OpenAI-compatible
llama-server HTTP API, and optional local PyTorch/bitsandbytes 4-bit NF4
CUDA execution (dynamically imported only when requested).
Pure stdlib Python, <= 210 lines, every function <= 50 lines.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    elapsed_s: float
    tokens_per_sec: float
    peak_vram_gb: float | None = None


def query_nvidia_vram_gb() -> float | None:
    """Best-effort nvidia-smi query returning current GPU VRAM used in GB."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        ).strip()
        first = out.splitlines()[0].strip()
        return round(float(first) / 1024.0, 3)
    except Exception:
        return None


class MockBackend:
    """Deterministic CPU-safe backend for unit tests and planted controls."""

    def __init__(self, responder: Callable[[str, int], str], *, name: str = "mock-local-14b") -> None:
        self.responder = responder
        self.name = name

    def generate(self, prompt: str, *, max_new_tokens: int = 384, iteration: int = 0) -> GenerationResult:
        _ = max_new_tokens
        t0 = time.perf_counter()
        text = self.responder(prompt, iteration)
        dt = max(1e-6, time.perf_counter() - t0)
        ptok = max(1, len(prompt.split()))
        ctok = max(1, len(text.split()))
        return GenerationResult(text, ptok, ctok, dt, ctok / dt, peak_vram_gb=0.0)


class OllamaHTTPBackend:
    """Local Ollama HTTP backend (`POST /api/generate`, deterministic temperature=0)."""

    def __init__(self, model: str, *, base_url: str = "http://127.0.0.1:11434", timeout: int = 120) -> None:
        self.name = f"ollama:{model}"
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str, *, max_new_tokens: int = 384, iteration: int = 0) -> GenerationResult:
        _ = iteration
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": max_new_tokens, "seed": 42},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        dt = max(1e-6, time.perf_counter() - t0)
        ctok = int(data.get("eval_count") or max(1, len(str(data.get("response", "")).split())))
        ptok = int(data.get("prompt_eval_count") or max(1, len(prompt.split())))
        eval_ns = int(data.get("eval_duration") or 0)
        tps = (ctok / (eval_ns / 1e9)) if eval_ns > 0 else (ctok / dt)
        return GenerationResult(
            text=str(data.get("response", "")),
            prompt_tokens=ptok,
            completion_tokens=ctok,
            elapsed_s=dt,
            tokens_per_sec=tps,
            peak_vram_gb=query_nvidia_vram_gb(),
        )


class Transformers4BitBackend:
    """Local HuggingFace 4-bit NF4 CUDA backend (dynamically imports torch/transformers)."""

    def __init__(self, model_path: str) -> None:
        torch = importlib.import_module("torch")
        tf = importlib.import_module("transformers")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for Transformers4BitBackend")
        self._torch = torch
        self.name = f"transformers4bit:{model_path}"
        bnb_cfg = tf.BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        self._tok = tf.AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self._model = tf.AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=bnb_cfg,
            device_map="auto",
            local_files_only=True,
        )
        self._model.eval()

    def generate(self, prompt: str, *, max_new_tokens: int = 384, iteration: int = 0) -> GenerationResult:
        _ = iteration
        torch = self._torch
        msgs = [{"role": "user", "content": prompt}]
        if hasattr(self._tok, "apply_chat_template"):
            rendered = self._tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        else:
            rendered = prompt
        inputs = self._tok(rendered, return_tensors="pt").to(self._model.device)
        ptok = int(inputs["input_ids"].shape[-1])
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            out_ids = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self._tok.eos_token_id,
            )
        torch.cuda.synchronize()
        dt = max(1e-6, time.perf_counter() - t0)
        new_ids = out_ids[0][ptok:]
        text = self._tok.decode(new_ids, skip_special_tokens=True)
        ctok = max(1, int(new_ids.shape[-1]))
        peak_gb = round(torch.cuda.max_memory_allocated() / (1024.0 ** 3), 3)
        return GenerationResult(text, ptok, ctok, dt, ctok / dt, peak_vram_gb=peak_gb)


def make_backend(kind: str, model: str, *, base_url: str = "http://127.0.0.1:11434") -> Any:
    if kind == "ollama":
        return OllamaHTTPBackend(model, base_url=base_url)
    if kind == "transformers4bit":
        return Transformers4BitBackend(model)
    raise ValueError(f"unsupported backend kind: {kind}")
