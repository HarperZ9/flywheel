"""Behavioral perception measurement: does the trained model answer a locate task
better under the criterion-CONSERVING encoding than the naive (collapsing) one?

For N seeded scenes, pose the same locate query under both encodings, hit the
served model, score by whether the true object name is the model's answer. If
conserving accuracy > naive accuracy, the transpiler is delivering usable
perception (criterion-conserving), not decoration. Honest: this measures a
behavioral gap, not internal J-space.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/mnt/c/dev/local-model")
from harness.perception_probe import make_scene, conserving_encode, naive_encode, scene_query


def ask(serve: str, prompt: str) -> str:
    body = json.dumps({"prompt": prompt, "system": "Answer with only the object name.",
                       "max_new_tokens": 16, "temperature": 0.0, "seed": 0}).encode()
    req = urllib.request.Request(serve.rstrip("/") + "/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["text"]


def score(answer: str, truth: str, names: list[str]) -> bool:
    a = answer.lower()
    hits = [(a.index(nm), nm) for nm in names if nm in a]
    return bool(hits) and min(hits)[1] == truth   # first-mentioned name is the truth


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", default="http://127.0.0.1:8765")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="/mnt/e/local-model-run/perception_scorecard.json")
    a = ap.parse_args()

    cons_ok = naive_ok = 0
    for seed in range(a.n):
        s = make_scene(seed)
        names = [o[0] for o in s.objects]
        qc = scene_query(s, conserving_encode(s))
        qn = scene_query(s, naive_encode(s))
        cons_ok += score(ask(a.serve, qc["prompt"]), qc["answer"], names)
        naive_ok += score(ask(a.serve, qn["prompt"]), qn["answer"], names)

    res = {"n": a.n, "conserving_acc": round(cons_ok / a.n, 3),
           "naive_acc": round(naive_ok / a.n, 3),
           "lift": round((cons_ok - naive_ok) / a.n, 3),
           "verdict": "PERCEPTION" if cons_ok > naive_ok else "NO-GAIN"}
    print(json.dumps(res, indent=2))
    Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"scorecard -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
