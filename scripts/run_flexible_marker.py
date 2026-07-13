"""Flexible-generalization marker (functional-access, NOT phenomenal): does ONE
conserving encoding support MULTIPLE functions? Per-function accuracy over the
same representation. >=3/4 functions handled => workspace-loaded (one rep, many
functions); <=1 => copyable but not flexibly usable. Honest labels only."""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/mnt/c/dev/local-model")
from harness.perception_probe import make_scene, conserving_encode, flexible_queries

FUNCS = ["locate", "nearest", "count_left", "quadrant"]


def ask(serve: str, prompt: str) -> str:
    body = json.dumps({"prompt": prompt, "system": "Answer concisely with only the answer.",
                       "max_new_tokens": 16, "temperature": 0.0, "seed": 0}).encode()
    req = urllib.request.Request(serve.rstrip("/") + "/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["text"]


def score(fn: str, answer: str, truth: str, names: list[str]) -> bool:
    a = answer.lower()
    if fn in ("locate", "nearest"):
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
    ap.add_argument("--out", default="/mnt/e/local-model-run/flexible_marker_scorecard.json")
    a = ap.parse_args()

    ok = {f: 0 for f in FUNCS}
    for seed in range(a.n):
        s = make_scene(seed)
        names = [o[0] for o in s.objects]
        q = flexible_queries(s, conserving_encode(s))
        for f in FUNCS:
            ok[f] += score(f, ask(a.serve, q[f]["prompt"]), q[f]["answer"], names)

    acc = {f: round(ok[f] / a.n, 3) for f in FUNCS}
    handled = sum(1 for f in FUNCS if acc[f] >= 0.6)
    res = {"n": a.n, "per_function_acc": acc, "functions_handled": handled,
           "marker": "flexible_generalization (functional-access, not phenomenal)",
           "verdict": "WORKSPACE-LOADED" if handled >= 3 else
                      ("PARTIAL" if handled == 2 else "COPY-ONLY")}
    print(json.dumps(res, indent=2))
    Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"scorecard -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
