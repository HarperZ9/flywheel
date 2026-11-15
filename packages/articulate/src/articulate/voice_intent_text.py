"""Plain-text output for voice intend and voice check."""
from . import voice_devices as vd

RANGE_LABELS = {"sentence_len_cv": "sentence length variation",
                "hedges_per_1k": "hedges per 1,000 words",
                "one_line_share": "share of one-sentence paragraphs"}


def _label(key):
    return vd.TELL_LABELS.get(key) or vd.WORK_LABELS.get(key) or RANGE_LABELS.get(key) or (
        "the line checker's devices" if key == "house-devices" else
        "the tool and its command" if key == "tool" else key)


def format_spec(spec):
    out = [f"Intent spec: {spec.get('name')}"]
    for key in ("goal", "audience", "stance"):
        if spec.get(key):
            out.append(f"  {key}: {spec[key]}")
    samples = spec.get("sources", {}).get("samples", [])
    if samples:
        out.append(f"  samples: {len(samples)} ({sum(s['words'] for s in samples)} words, "
                   "kept as hashes and counts)")
    out.append("\nThe draft should:")
    out += [f"  - {_label(k)}" for k, v in spec.get("wants", {}).items() if v]
    out.append("\nThe draft should leave out:")
    out += [f"  - {_label(k)}" for k, v in spec.get("limits", {}).items() if v == 0]
    out.append("\nPlan:")
    out += [f"  {i}. {step}" for i, step in enumerate(spec.get("plan", []), 1)]
    return "\n".join(out)


def _value(c):
    v, b = c["value"], c["bound"]
    if isinstance(v, float) or isinstance(b, float):
        sign = "at most" if c["kind"] == "limit" else "at least"
        return f"{v:.2f}, needs {sign} {b}"
    return f"found {v}, allowed {b}" if c["kind"] == "limit" else f"found {v}, needs {b}"


def format_check(report, path=None):
    head = f"{path}: " if path else ""
    out = [f"{head}{report['score']}/100 against '{report['spec']}' "
           f"({report['met']} of {report['total']} checks met, {report['words']} words)"]
    for c in (c for c in report["checks"] if not c["ok"]):
        out.append(f"  miss  {_label(c['id'])}: {_value(c)}")
        for e in c.get("examples", []):
            detail = f" [{e['detail']}]" if e.get("detail") else ""
            out.append(f"        line {e['line']}{detail}: {e['snippet']}")
        if c["note"]:
            out.append(f"        {'why' if c['kind'] == 'limit' else 'fix'}: {c['note']}")
    met = [c for c in report["checks"] if c["ok"] and c["kind"] == "want"]
    if met:
        out.append("  met   " + "; ".join(_label(c["id"]) for c in met))
    out.append(f"  {report['score_means']}")
    return "\n".join(out)
