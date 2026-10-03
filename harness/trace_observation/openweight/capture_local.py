"""capture_local.py -- raw reasoning and option logprobs from a local Ollama model.

The harness writes the chat prompt itself (raw mode), so it controls the
reasoning span: it can sample a span, cut it, edit it, and read the answer that
follows. That control is access class A2 on a local open-weight model; logprobs
add A3. None of this applies to a closed model, where the same components
report REASONING_WRITE_UNAVAILABLE.

The transport is injectable. OllamaBackend posts to a local server; tests pass
a recorded-response transport. Seed 0 is refused: round 1 found Ollama treats
it as unseeded, so it would break sampling re-derivation.
"""
from __future__ import annotations

import json
import math
import urllib.request

from ..adapters import ollama as ollama_adapter

DEFAULT_URL = "http://localhost:11434/api/generate"
SAMPLE = {"temperature": 0.6, "top_k": 20, "top_p": 0.95, "repeat_penalty": 1.0}
READOUT_TAIL = "\n</think>\n\nThe answer is ("
LETTERS = "ABCD"


def http_post(url: str, timeout: float = 600.0):
    def post(body: dict) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- local server
            return json.loads(resp.read())
    return post


def qwen_head(user_text: str) -> str:
    """Qwen3 chat prompt opened at the assistant's think span."""
    return f"<|im_start|>user\n{user_text}<|im_end|>\n<|im_start|>assistant\n<think>\n"


def letter_probs(top: list) -> dict:
    """Option distribution from one position's top logprobs, renormalized over A-D."""
    mass = {L: 0.0 for L in LETTERS}
    for x in top or []:
        t = str(x.get("token", "")).strip()
        if t in mass:
            mass[t] += math.exp(float(x["logprob"]))
    total = sum(mass.values())
    if total <= 0:
        return {"status": "no_letter"}
    probs = {L: mass[L] / total for L in LETTERS}
    return {"status": "ok", "probs": probs, "argmax": max(LETTERS, key=lambda L: probs[L])}


class OllamaBackend:
    def __init__(self, model: str, post=None, url: str = DEFAULT_URL) -> None:
        self.model = model
        self.post = post or http_post(url)

    def _call(self, prompt: str, options: dict, **extra) -> dict:
        if int(options.get("seed", 1)) == 0:
            raise ValueError("seed 0 is unseeded on Ollama; use a nonzero seed")
        body = {"model": self.model, "prompt": prompt, "raw": True, "stream": False,
                "options": options, **extra}
        return body, self.post(body)

    def span(self, head: str, seed: int, budget: int, logprobs: bool = False) -> dict:
        """Sample reasoning until </think> or the budget."""
        opts = dict(SAMPLE, seed=seed, num_predict=budget, stop=["</think>"])
        body, r = self._call(head, opts, **({"logprobs": True} if logprobs else {}))
        text = (r.get("thinking") or "") + (r.get("response") or "")
        tokens = [x["token"] for x in r.get("logprobs") or []] or None
        cap = ollama_adapter.capture(body, {"thinking": text, "response": "",
                                            "done_reason": r.get("done_reason"),
                                            "logprobs": r.get("logprobs"), "model": self.model},
                                     run_id="span")
        return {"text": text, "tokens": tokens, "closed": r.get("done_reason") == "stop",
                "budget_hit": r.get("done_reason") == "length", "record": cap.record}

    def readout(self, head: str, span: str) -> dict:
        """Close the span, force the answer stem, read the letter distribution."""
        opts = {"temperature": 0, "seed": 1, "num_predict": 1}
        _, r = self._call(head + span.rstrip("\n") + READOUT_TAIL, opts,
                          logprobs=True, top_logprobs=20)
        lp = r.get("logprobs") or []
        if not lp:
            return {"status": "no_logprobs"}
        return letter_probs(lp[0].get("top_logprobs") or [])

    def answer(self, head: str, span: str, seed: int, budget: int = 2048) -> str:
        opts = dict(SAMPLE, seed=seed, num_predict=budget)
        _, r = self._call(head + span.rstrip("\n") + "\n</think>\n\n", opts)
        return ((r.get("thinking") or "") + (r.get("response") or "")).strip()


class RecordedTransport:
    """Replays recorded responses keyed by (prompt, seed). Unknown keys raise."""

    def __init__(self, table: dict) -> None:
        self.table = table
        self.calls = []

    @staticmethod
    def key(body: dict) -> str:
        return json.dumps([body["prompt"], body["options"].get("seed")], ensure_ascii=False)

    def __call__(self, body: dict) -> dict:
        self.calls.append(body)
        k = self.key(body)
        if k not in self.table:
            raise KeyError(f"no recorded response for this prompt and seed ({len(body['prompt'])} chars)")
        return self.table[k]
