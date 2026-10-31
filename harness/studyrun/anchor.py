"""Truth anchor: a study that scores an update-size metric must also score a truth-anchored one.

F95 MT3: update size (transfer entropy, weight-change norm) ranked a false arm at or above the
true arm in two of three toys. An update-size metric says how much a learner moved, never whether
it moved toward the truth. So when a spec declares one, it must also declare a measure tied to
the target (accuracy, return, target choice) and score it in a verdict. The rule runs only when a
new lock is written (`studyrun prereg`); studies locked before it stay valid as they ran.

A spec declares measures in two ways, and both are read:
  * explicitly, in an optional top-level list: "measures": [{"name": "te", "kind": "update_size"},
    {"name": "accuracy", "kind": "truth_anchored"}]; and
  * implicitly, by the metric names its verdict rules read (left and right fields).
Name matching splits on non-alphanumeric characters and camel case, so "analysis.te_true_arm" and
"analysis.weightChangeNorm" both match. A truth-anchored measure counts only when some verdict
rule reads it: an anchor nobody scores is not beside the update-size metric.
"""
import re

UPDATE_SIZE_TERMS = (
    ("transfer", "entropy"), ("te",), ("weight", "change"), ("weight", "norm"), ("delta", "w"),
    ("dw",), ("kl", "shift"), ("kl",), ("dq",), ("d", "q"), ("delta", "q"), ("update", "size"),
    ("update", "norm"), ("grad", "norm"), ("gradient", "norm"), ("param", "shift"),
)
TRUTH_TERMS = (
    ("accuracy",), ("acc",), ("return",), ("returns",), ("reward",), ("target", "choice"),
    ("correct",), ("hit", "rate"), ("true", "arm", "choice"), ("regret",), ("auc",), ("f1",),
    ("error",), ("mse",), ("loglik",), ("log", "likelihood"), ("brier",),
)
KINDS = ("update_size", "truth_anchored", "other")


def _tokens(name):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
    s = s.replace("|", " abs ")
    return [t for t in re.split(r"[^A-Za-z0-9]+", s.lower()) if t]


def _matches(name, terms):
    toks = _tokens(name)
    for term in terms:
        n = len(term)
        if any(tuple(toks[i:i + n]) == term for i in range(len(toks) - n + 1)):
            return True
    return False


def _verdict_refs(spec):
    refs = []
    for rules in (spec.get("verdicts") or {}).values():
        for rule in rules if isinstance(rules, list) else []:
            for side in ("left", "right"):
                v = rule.get(side) if isinstance(rule, dict) else None
                if isinstance(v, str):
                    refs.append(v)
    return refs


def measures(spec):
    """Return (update_size, truth_scored, problems) read from the spec."""
    problems, update, truth_declared = [], [], []
    for i, m in enumerate(spec.get("measures") or []):
        if not isinstance(m, dict) or not m.get("name") or m.get("kind") not in KINDS:
            problems.append(f"measures[{i}]: needs a name and kind in {KINDS}")
            continue
        if m["kind"] == "update_size":
            update.append(m["name"])
        elif m["kind"] == "truth_anchored":
            truth_declared.append(m["name"])
    refs = _verdict_refs(spec)
    update += [r for r in refs if _matches(r, UPDATE_SIZE_TERMS) and r not in update]
    truth = [r for r in refs if _matches(r, TRUTH_TERMS)]
    for name in truth_declared:
        if any(name == r or _tokens(name) == _tokens(r)[-len(_tokens(name)):] for r in refs):
            truth.append(name)
        else:
            problems.append(f"measures: truth-anchored '{name}' is declared but no verdict rule reads it")
    return update, truth, problems


def problems(spec):
    """Problems that block a new lock. Empty when the spec is fine."""
    update, truth, bad = measures(spec)
    if update and not truth:
        bad.append("update-size metric " + ", ".join(sorted(set(update))) + " has no truth-anchored "
                   "measure beside it (accuracy, return, target choice or similar) in a verdict rule; "
                   "update size ranked a false arm at or above the true arm in two of three toys (F95 MT3)")
    return bad
