"""Disentangle the COPY-ONLY finding: is the opaque grid-label FORMAT the
bottleneck for flexible use, or can the model just not do the spatial reasoning?

Sweep three encodings over the SAME reasoning functions (nearest/count/quadrant):
  labels    — conserving grid labels only (the COPY-ONLY encoding)
  reasoning — labels + decoded coords (transpile-derived, reasoning-friendly)
  raw       — full-precision coords only (control: format-independent ceiling)

If reasoning/raw >> labels, the FORMAT was the bottleneck (a real tooling fix).
If all three are low, the model can't do the reasoning regardless of format.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/mnt/c/dev/local-model")
from harness.perception_probe import (make_scene, conserving_encode, reasoning_encode,
                                       raw_encode, flexible_queries)

ENCODERS = {"labels": conserving_encode, "reasoning": reasoning_encode, "raw": raw_encode}
FUNCS = ["nearest", "count_left", "quadrant"]


def ask(serve: str, prompt: str) -> str:
    body = json.dumps({"prompt": prompt, "system": "Answer concisely with only the answer.",
                       "max_new_tokens": 16, "temperature": 0.0, "seed": 0}).encode()
    req = urllib.request.Request(serve.rstrip("/") + "/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["text"]


def score(fn: str, answer: str, truth: str, names: list[str]) -> bool:
    a = answer.lower()
    if fn == "nearest":
        hits = [(a.index(nm), nm) for nm in names if nm in a]
        return bool(hits) and min(hits)[1] == truth
    if fn == "count_left":
        m = re.search(r"\d+", a)
        return bool(m) and m.group(0) == truth
    if fn == "quadrant":
        return truth in a.replace(" ", "-")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", default="http://127.0.0.1:8765")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="/mnt/e/local-model-run/encoding_sweep_scorecard.json")
    a = ap.parse_args()

    result = {}
    for enc_name, enc_fn in ENCODERS.items():
        ok = {f: 0 for f in FUNCS}
        for seed in range(a.n):
            s = make_scene(seed)
            names = [o[0] for o in s.objects]
            q = flexible_queries(s, enc_fn(s))
            for f in FUNCS:
                ok[f] += score(f, ask(a.serve, q[f]["prompt"]), q[f]["answer"], names)
        acc = {f: round(ok[f] / a.n, 3) for f in FUNCS}
        acc["_mean"] = round(sum(ok.values()) / (a.n * len(FUNCS)), 3)
        result[enc_name] = acc

    labels_m, reason_m, raw_m = (result[k]["_mean"] for k in ("labels", "reasoning", "raw"))
    if raw_m < 0.4:
        verdict = "MODEL-LIMITED (reasoning fails even with raw coords)"
    elif reason_m - labels_m >= 0.2:
        verdict = "FORMAT-BOTTLENECK (reasoning-friendly encoding recovers flexible use)"
    else:
        verdict = "INCONCLUSIVE"
    out = {"n": a.n, "per_encoding": result, "verdict": verdict,
           "means": {"labels": labels_m, "reasoning": reason_m, "raw": raw_m}}
    print(json.dumps(out, indent=2))
    Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"scorecard -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
