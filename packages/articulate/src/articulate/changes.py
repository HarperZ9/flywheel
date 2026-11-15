"""The change report for an edit: what changed, sentence by sentence.

`for_result(original, result)` reads an edit result (fix, polish or submit)
and pairs the sentences of the original with the sentences of the accepted
text, paragraph by paragraph, using difflib over whitespace-normalized
sentences. A merged or split sentence shows as one record spanning several
sentences. Each changed record gives the text before and after, and the local
findings (rule id and label) on the before sentence that are gone and that
remain, plus any finding the new sentence adds. The report also lists each
paragraph the guard refused, with its reasons, and each allowed change.

The findings columns show what the checker saw; they do not show why the editor
changed a sentence. `survival` grades how much of each property came through
(articulate.survival): items, devices, rhythm, order and register, each as a
clarity value. Standard library only.
"""
from collections import Counter
import difflib
import re

from . import survival

SCHEMA = "articulate/changes/v2"
SCOPE = ("Pairs each changed sentence with the sentence before the edit. Lists the "
         "findings that each edit removed, kept or added.")
_PARAGRAPH = re.compile(r"\r?\n[ \t]*\r?\n(?:[ \t]*\r?\n)*")
_SENT_END = re.compile("(?<=[.!?])[\"'”’)\\]]*(\\s+)")


def _paragraphs(text):
    """(start, end) of each paragraph, split where the meaning guard splits."""
    spans, pos = [], 0
    for m in _PARAGRAPH.finditer(text):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(text)))
    return spans


def _sentences(text, start, end):
    """(start, end) of each sentence inside text[start:end]."""
    out, pos, block = [], start, text[start:end]
    for m in _SENT_END.finditer(block):
        stop = start + m.start(1)
        if text[pos:stop].strip():
            out.append((pos, stop))
        pos = start + m.end()
    if text[pos:end].strip():
        out.append((pos, end))
    return out


def _in(findings, segs):
    if not segs:
        return []
    lo, hi = segs[0][0], segs[-1][1]
    return [f for f in findings if lo <= f["start"] < hi]


def _diff_findings(before, after):
    """(gone, remaining, added) as rule_id and label records, counted per rule."""
    left, right = Counter(f["rule_id"] for f in before), Counter(f["rule_id"] for f in after)
    gone, remaining, seen = [], [], Counter()
    for f in before:
        seen[f["rule_id"]] += 1
        rec = {"rule_id": f["rule_id"], "label": f.get("label", f["category"])}
        (remaining if seen[f["rule_id"]] <= right[f["rule_id"]] else gone).append(rec)
    added, seen = [], Counter()
    for f in after:
        seen[f["rule_id"]] += 1
        if seen[f["rule_id"]] > left[f["rule_id"]]:
            added.append({"rule_id": f["rule_id"], "label": f.get("label", f["category"])})
    return gone, remaining, added


def _all(result):
    return result["high"] + result["medium"] + result["low"]


def _paragraph_records(index, original, final, spans, found):
    a_segs, b_segs = _sentences(original, *spans[0]), _sentences(final, *spans[1])
    norm = [[" ".join(t[s:e].split()) for s, e in segs]
            for t, segs in ((original, a_segs), (final, b_segs))]
    out = []
    matcher = difflib.SequenceMatcher(None, norm[0], norm[1], autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        before, after = a_segs[i1:i2], b_segs[j1:j2]
        gone, remaining, added = _diff_findings(_in(found[0], before), _in(found[1], after))
        out.append({"paragraph": index, "op": op,
                    "line": original.count("\n", 0, (before or [spans[0]])[0][0]) + 1,
                    "before": original[before[0][0]:before[-1][1]] if before else "",
                    "after": final[after[0][0]:after[-1][1]] if after else "",
                    "findings_gone": gone, "findings_remaining": remaining,
                    "findings_added": added})
    return out


def build(original, final, check, refused=(), allowed_changes=()):
    """The change report. `check(text)` returns a detector-shaped result."""
    found = (_all(check(original)), _all(check(final)))
    old, new = _paragraphs(original), _paragraphs(final)
    if len(old) != len(new):
        old, new = [(0, len(original))], [(0, len(final))]
    records = []
    for i, (a, b) in enumerate(zip(old, new)):
        if original[a[0]:a[1]] != final[b[0]:b[1]]:
            records.extend(_paragraph_records(i, original, final, (a, b), found))
    return {"schema": SCHEMA, "sentences": records,
            "refused": [{"paragraph": r.get("paragraph"), "reasons": list(r.get("reasons", []))}
                        for r in refused],
            "allowed_changes": list(allowed_changes),
            "summary": {"changed": len(records), "findings_before": len(found[0]),
                        "findings_after": len(found[1])},
            "survival": survival.compare(original, final),
            "scope": SCOPE}


def for_result(original, result):
    """The change report for an accepted edit result, or None for a host plan."""
    receipt = result.get("receipt")
    if not isinstance(receipt, dict) or "text" not in result:
        return None
    from .host_edit import check_under
    profile = receipt.get("settings", {}).get("profile")
    return build(original, result["text"], lambda text: check_under(text, profile),
                 result.get("refused", []), result.get("allowed_changes", []))


def attach(original, result):
    """Add `changes` to an accepted edit result in place; return the result."""
    report = for_result(original, result)
    if report is not None:
        result["changes"] = report
    return result


def _clip(text, n=160):
    one = " ".join(text.split())
    return one if len(one) <= n else one[:n - 3] + "..."


def format_report(rep, name=""):
    """The readable change report."""
    s = rep["summary"]
    lines = ["[changes] %s%d changed sentence group(s); findings %d -> %d"
             % (name + ": " if name else "", s["changed"], s["findings_before"], s["findings_after"])]
    for c in rep["sentences"]:
        lines.append("  paragraph %d, L%d, %s" % (c["paragraph"] + 1, c["line"], c["op"]))
        if c["before"]:
            lines.append("    - " + _clip(c["before"]))
        if c["after"]:
            lines.append("    + " + _clip(c["after"]))
        for key, word in (("findings_gone", "gone"), ("findings_remaining", "remains"),
                          ("findings_added", "added")):
            lines.extend("      %s: %s (%s)" % (word, f["rule_id"], f["label"]) for f in c[key])
    for r in rep["refused"]:
        where = "the whole text" if r["paragraph"] is None else "paragraph %d" % (r["paragraph"] + 1)
        lines.append("[changes] kept %s: %s" % (where, "; ".join(r["reasons"])))
    for a in rep["allowed_changes"]:
        lines.append("[changes] allowed %s change in paragraph %d" % (a["kind"], a["paragraph"] + 1))
    if rep.get("survival"):
        lines.append("[changes] survival (clarity: 1 kept, below 1 lost, above 1 gained):")
        lines.extend(survival.format_lines(rep["survival"]))
    lines.append("[changes] Read each pair to check the meaning held.")
    return "\n".join(lines)
