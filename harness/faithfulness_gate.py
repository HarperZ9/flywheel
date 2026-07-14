"""faithfulness_gate.py -- two judges, one witnessed disagreement.

Whether a formal statement faithfully renders its informal claim is
judged, not computed, and judge choice moves published faithfulness
scores by twenty-five points or more. The field's habit is to average
judges into one confident-looking number; this gate refuses. Every
pair gets both verdicts on the record, agreement is counted, and the
disagreement rate is reported as a first-class result: where the
judges split IS the finding. A judge that crashes yields an
unverifiable row with the reason, never a synthesized verdict, and no
single blended score exists anywhere in the output by design.
"""
from __future__ import annotations

SCHEMA = "flywheel.faithfulness-disagreement/v1"


def _run_judge(judge, pair) -> tuple:
    try:
        return bool(judge(pair)), ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def judge_pairs(pairs: list, *, judge_a, judge_b,
                names: tuple = ("judge_a", "judge_b")) -> dict:
    """Run both judges over (informal, formal) pairs. Each judge is a
    callable(pair) -> bool. Returns every verdict pair, the
    disagreement count and rate, and never a blended score."""
    rows = []
    disagreements = 0
    for p in pairs or []:
        va, ea = _run_judge(judge_a, p)
        vb, eb = _run_judge(judge_b, p)
        agree = va is not None and vb is not None and va == vb
        if not agree:
            disagreements += 1
        note = "; ".join(x for x in (ea, eb) if x)
        rows.append({"informal": str(p.get("informal", ""))[:200],
                     "formal": str(p.get("formal", ""))[:200],
                     "judge_a": va, "judge_b": vb, "agree": agree,
                     "note": note})
    n = len(rows)
    return {"schema": SCHEMA, "n_pairs": n, "judges": list(names),
            "rows": rows, "disagreements": disagreements,
            "disagreement_rate": round(disagreements / n, 4) if n else 0.0,
            "note": "both verdicts stay on the record; averaging judges "
                    "into one number is the failure this gate refuses"}
