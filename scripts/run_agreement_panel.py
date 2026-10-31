"""run_agreement_panel.py -- majority agreement against the deterministic checks.

Measures FLYWHEEL-OPPORTUNITIES item 7 with the bounds written before any run:
each voter answers CORRECT or WRONG once per case (40 wrong subjects from
tests/fixtures/checks/false_accepts_v1.json and their 40 fixed twins), a strict
majority of CORRECT accepts, and the counts go beside the checks' 38 of 40.

  python scripts/run_agreement_panel.py --out DIR --live \
      --models qwen3:8b,olmo2:7b,qwen2.5:7b,qwen2.5-coder:14b-instruct-q4_K_M,qwen3-coder:30b

Without --live nothing is called; the script prints the plan. Rows append to
DIR/rows.jsonl one call at a time and a rerun skips finished calls, so a stopped
run resumes. Panels: the first 3 models and all 5. Local Ollama only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import agreement_vote as av  # noqa: E402
from harness.checks import PASS, run  # noqa: E402

CORPUS_PATH = ROOT / "tests" / "fixtures" / "checks" / "false_accepts_v1.json"


def deterministic(corpus: dict) -> dict:
    return {it["id"]: run(it["kind"], it["subject"], it["spec"]).verdict != PASS
            for it in corpus["items"]}


def measure(corpus: dict, voters: dict, out: Path, panels: list) -> dict:
    rows = av.run_votes(corpus, voters, out / "rows.jsonl")
    det = deterministic(corpus)
    corpus_sha = hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest()
    rows_sha = hashlib.sha256((out / "rows.jsonl").read_bytes()).hexdigest()
    result = {"corpus_sha256": corpus_sha, "rows_sha256": rows_sha,
              "panels": [av.summarize(corpus, rows, p, det) for p in panels]}
    (out / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main(argv: "list | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", default="qwen3:8b,olmo2:7b,qwen2.5:7b,"
                                        "qwen2.5-coder:14b-instruct-q4_K_M,qwen3-coder:30b")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--live", action="store_true", help="call the local models")
    args = ap.parse_args(argv)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    panels = [models[:3], models] if len(models) > 3 else [models]
    plan = {"models": models, "panels": panels, "cases": len(av.cases(corpus)),
            "calls": len(models) * len(av.cases(corpus)), "template_sha256": av.TEMPLATE_SHA256}
    if not args.live:
        print(json.dumps(plan, indent=1))
        print("dry run: pass --live to call the models")
        return 0
    voters = {m: av.ollama_voter(m, args.ollama_url) for m in models}
    result = measure(corpus, voters, Path(args.out), panels)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
