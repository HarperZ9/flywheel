"""Dialogue and character voice: the audit behind `articulate dialogue`.

audit(records, sheets, project) runs three passes over spoken lines:
  1. the dialogue profile (dialogue_rules): shapes that make speech sound written;
  2. the voice sheets (dialogue_sheet): register, length, never-words, knowledge;
  3. blind attribution (dialogue_attrib): can a classifier tell who is talking?
and returns one report. Each line gets a score, the sum of its findings' weights.
Nothing is edited. The report says where to look; a writer decides what to change.
"""
from collections import Counter, defaultdict

from . import dialogue_attrib, dialogue_rules, dialogue_sheet
from .dialogue_lexicon import words

FORMAT = "articulate-dialogue-report/2"
GENERIC_WEIGHT = 1
SCOPE = ("Marks lines to read and scores how distinct each voice is. A deliberate "
         "epigram is still marked. One repeated habit can make a voice score as distinct.")


def _generic_cut(k):
    return max(3, k // 4)


def audit(records, sheets=None, project=None, *, min_lines=None, theme_words=None):
    sheets, project = sheets or {}, project or {}
    themes = theme_words if theme_words is not None else project.get("theme_words", [])
    floor = min_lines or project.get("min_lines", 20)
    proper = dialogue_rules.proper_nouns(records)
    att = dialogue_attrib.attribute(records, min_lines=floor)
    k = len(att["speakers"])
    by_index = {r["index"]: r for r in att["per_line"]}
    detail = []
    for i, rec in enumerate(records):
        found = dialogue_rules.check_line(rec["text"], themes, proper)
        sheet = sheets.get(rec["speaker"].upper())
        if sheet:
            found += dialogue_sheet.check_line(rec, sheet, proper)
        a = by_index.get(i)
        if (a and k >= 3 and a["rank"] > _generic_cut(k) and a["p_true"] < 1 / k
                and len(words(rec["text"])) >= 6):
            found.append({"check": "generic", "weight": GENERIC_WEIGHT,
                          "label": f"could belong to anyone: the true speaker ranks {a['rank']} "
                                   f"of {k} (top guess {a['top']})", "excerpt": ""})
        detail.append(dict(rec, score=sum(f["weight"] for f in found), findings=found,
                           attribution=a and {"rank": a["rank"], "p_true": a["p_true"],
                                              "top": a["top"]}))
    return {"format": FORMAT, "lines": len(records), "themes": list(themes),
            "speakers": _speakers(detail, sheets, att),
            "groups": _groups(detail),
            "attribution": {"chance": att["chance"], "folds": att["folds"],
                            "min_lines": att["min_lines"], "block_size": att.get("block_size"),
                            "speakers_scored": k},
            "checks": dict(Counter(f["check"] for d in detail for f in d["findings"])),
            "detail": detail, "scope": SCOPE}


def _epigram(d):
    return any(f["check"] in dialogue_rules.EPIGRAM_CHECKS for f in d["findings"])


def _speakers(detail, sheets, att):
    by = defaultdict(list)
    for d in detail:
        by[d["speaker"]].append(d)
    out = {}
    for name, rows in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        sheet = sheets.get(name.upper())
        entry = {"lines": len(rows), "flagged": sum(1 for d in rows if d["findings"]),
                 "epigram_lines": sum(1 for d in rows if _epigram(d)),
                 "mean_words": round(sum(len(words(d["text"])) for d in rows) / len(rows), 1),
                 "sheet": bool(sheet), "distinctiveness": att["speakers"].get(name)}
        if sheet:
            entry.update({k: round(v, 3) for k, v in dialogue_sheet.usage(rows, sheet).items()})
        out[name] = entry
    return out


def _groups(detail):
    out = defaultdict(lambda: {"lines": 0, "epigram_lines": 0, "flagged": 0})
    for d in detail:
        g = out[d.get("group") or "-"]
        g["lines"] += 1
        g["epigram_lines"] += _epigram(d)
        g["flagged"] += bool(d["findings"])
    return dict(sorted(out.items()))


def worst(report, n=30):
    rows = [d for d in report["detail"] if d["score"] > 0]
    rows.sort(key=lambda d: (-d["score"], d["file"], d["line"]))
    return rows[:n]


def gate(report, *, max_epigram_rate=0.01, fail_checks=("never", "knowledge-leak"),
         min_lift=None):
    """Pass or fail for CI. The default epigram ceiling, 1 percent of lines, sits above
    every naturalistic source in the calibration set and below Wilde, who writes
    epigrams on purpose (docs/dialogue.md has the figures)."""
    reasons = []
    n = report["lines"] or 1
    epi = sum(1 for d in report["detail"] if _epigram(d))
    if epi / n > max_epigram_rate:
        reasons.append(f"{epi} of {report['lines']} lines carry an epigram shape "
                       f"({epi / n:.1%} > {max_epigram_rate:.1%})")
    for check in fail_checks:
        c = report["checks"].get(check, 0)
        if c:
            reasons.append(f"{c} {check} finding(s)")
    chance = report["attribution"]["chance"]
    if min_lift and chance:
        for name, s in report["speakers"].items():
            dist = s.get("distinctiveness")
            if s["sheet"] and dist and dist["interval"][1] < min_lift * chance:
                reasons.append(f"{name}: attribution {dist['accuracy']:.2f} "
                               f"(upper bound {dist['interval'][1]:.2f}) below "
                               f"{min_lift:g} x chance {chance:.2f}")
    return {"passed": not reasons, "reasons": reasons}


def summary_table(report):
    chance = report["attribution"]["chance"]
    head = (f"{'speaker':14} {'lines':>5} {'flag':>5} {'epi':>4} {'words':>5} "
            f"{'attrib':>6} {'95% interval':>13} {'5-line':>6}  sheet")
    out = [head, "-" * len(head)]
    for name, s in report["speakers"].items():
        d = s.get("distinctiveness")
        acc = f"{d['accuracy']:.2f}" if d else "-"
        ci = f"{d['interval'][0]:.2f}-{d['interval'][1]:.2f}" if d else "-"
        blk = f"{d['block']['accuracy']:.2f}" if d and d.get("block") else "-"
        out.append(f"{name[:14]:14} {s['lines']:5} {s['flagged']:5} {s['epigram_lines']:4} "
                   f"{s['mean_words']:5} {acc:>6} {ci:>13} {blk:>6}  {'yes' if s['sheet'] else ''}")
    if chance:
        out.append(f"chance for attribution: {chance:.3f} "
                   f"({report['attribution']['speakers_scored']} speakers with "
                   f"{report['attribution']['min_lines']}+ lines)")
    return "\n".join(out)
