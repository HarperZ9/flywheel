"""Verdict rules: a preregistered condition list per prediction, evaluated fail-closed.

A rule is {"left": path, "op": ">", "right": path or number}. Paths read the run result, for
example "analysis.delta" or "controls.C1.q95". A rule that reads an unusable control, or a path
that is missing, is not testable. Verdict per prediction:
  PASS        every rule holds;
  FAIL        some testable rule fails;
  UNTESTABLE  no testable rule fails, but some rule could not be tested.
"""
import operator

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


def get(result, path):
    cur = result
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def _control_of(path):
    parts = path.split(".")
    return parts[1] if len(parts) > 2 and parts[0] == "controls" else None


def _side(result, x):
    if isinstance(x, (int, float)):
        return x, None
    ctl = _control_of(x)
    if ctl and not result["controls"].get(ctl, {}).get("usable", False):
        return None, f"control {ctl} unusable"
    try:
        return get(result, x), None
    except (KeyError, IndexError, ValueError):
        return None, f"missing {x}"


def rule(result, r):
    left, why_l = _side(result, r["left"])
    right, why_r = _side(result, r["right"])
    why = why_l or why_r
    row = {"rule": f"{r['left']} {r['op']} {r['right']}", "left": left, "right": right}
    if why:
        return {**row, "holds": None, "why": why}
    return {**row, "holds": bool(OPS[r["op"]](left, right))}


def judge(result, verdicts):
    out = {}
    for name, rules in verdicts.items():
        rows = [rule(result, r) for r in rules]
        holds = [r["holds"] for r in rows]
        if any(h is False for h in holds):
            v = "FAIL"
        elif any(h is None for h in holds):
            v = "UNTESTABLE"
        else:
            v = "PASS"
        out[name] = {"verdict": v, "rules": rows}
    return out
