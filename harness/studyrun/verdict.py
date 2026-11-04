"""Verdict rules: a preregistered condition list per prediction, evaluated fail-closed.

A rule is {"left": path, "op": ">", "right": path or number}. Paths read the run result, for
example "analysis.delta" or "controls.C1.q95". A rule that reads an unusable control, or a path
that is missing, is not testable. Verdict per prediction:
  PASS        every rule holds;
  FAIL        some testable rule fails;
  UNTESTABLE  no testable rule fails, but some rule could not be tested.

Paths (upgrade 2026-11-02, F674 `verdictpathdots`). A string path splits on dots. A key that holds a
dot is written with the dot escaped, "analysis.bh.D1_overlap_hw\\.p_score" in JSON (one backslash
in the string), or the whole path is given as a list of keys, ["analysis", "bh", "D1_overlap_hw.p_score"].
A backslash before any other character stands for that character. Paths without a backslash parse
exactly as before, so every older spec reads the same values.
"""
import operator

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


def split_path(path):
    """Path (string with escapes, or list of keys) -> list of string keys."""
    if isinstance(path, (list, tuple)):
        return [str(p) for p in path]
    parts, cur, esc = [], [], False
    for ch in str(path):
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ".":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if esc:
        cur.append("\\")
    parts.append("".join(cur))
    return parts


def show(path):
    """A path as text, for messages and rule rows (lists shown with escaped dots)."""
    if isinstance(path, (list, tuple)):
        return ".".join(str(p).replace("\\", "\\\\").replace(".", "\\.") for p in path)
    return str(path)


def is_path(x):
    return isinstance(x, str) or (isinstance(x, (list, tuple)) and all(isinstance(p, (str, int)) for p in x))


def _hint(cur, part, rest):
    """When a dict holds a key that contains a dot and matches the start of what is left, say so."""
    if not isinstance(cur, dict):
        return ""
    joined = ".".join([part] + rest)
    hits = [k for k in cur if isinstance(k, str) and "." in k and joined.startswith(k)]
    if hits:
        k = max(hits, key=len)
        return f"; key '{k}' holds a dot: escape it as '{k.replace('.', chr(92) + '.')}' or use a list path"
    return ""


def get(result, path):
    cur = result
    parts = split_path(path)
    for i, part in enumerate(parts):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            err = KeyError(show(path))
            err.hint = _hint(cur, part, parts[i + 1:])
            raise err
    return cur


def _control_of(path):
    parts = split_path(path)
    return parts[1] if len(parts) > 2 and parts[0] == "controls" else None


def _side(result, x):
    if isinstance(x, bool) or isinstance(x, (int, float)):
        return x, None
    ctl = _control_of(x)
    if ctl and not result["controls"].get(ctl, {}).get("usable", False):
        return None, f"control {ctl} unusable"
    try:
        return get(result, x), None
    except KeyError as e:
        return None, f"missing {show(x)}{getattr(e, 'hint', '')}"
    except (IndexError, ValueError):
        return None, f"missing {show(x)}"


def rule(result, r):
    left, why_l = _side(result, r["left"])
    right, why_r = _side(result, r["right"])
    why = why_l or why_r
    row = {"rule": f"{show(r['left'])} {r['op']} {show(r['right'])}", "left": left, "right": right}
    if why:
        return {**row, "holds": None, "why": why}
    return {**row, "holds": bool(OPS[r["op"]](left, right))}


def judge(result, verdicts, binding=None):
    """binding: optional {name: {"binding": bool, ...}} from the power gate; copied onto each verdict."""
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
        if binding is not None and name in binding:
            out[name].update(binding[name])
    return out


def unresolved(result, verdicts):
    """Every verdict path that does not resolve on a result: [(verdict, path, why)]. Used at lock time."""
    bad = []
    for name, rules in verdicts.items():
        for r in rules:
            for side in ("left", "right"):
                x = r.get(side)
                if isinstance(x, bool) or isinstance(x, (int, float)):
                    continue
                try:
                    get(result, x)
                except KeyError as e:
                    bad.append((name, show(x), f"missing{getattr(e, 'hint', '')}"))
                except (IndexError, ValueError):
                    bad.append((name, show(x), "missing"))
    return bad
