"""Markdown rendering of a dialogue report, for a design folder or a pull request."""
from . import dialogue

_ESC = str.maketrans({"|": "\\|", "\n": " "})


def _cell(text, n=160):
    text = text.translate(_ESC)
    return text if len(text) <= n else text[:n - 3] + "..."


def _reasons(d):
    return "; ".join(f["label"] + (f" ({f['excerpt']})" if f.get("excerpt") and
                                   f["check"] not in ("generic",) else "")
                     for f in d["findings"])


def markdown(report, *, title="Voice audit", worst_n=30, preamble=""):
    out = [f"# {title}", ""]
    if preamble:
        out += [preamble.strip(), ""]
    n = report["lines"]
    epi = sum(g["epigram_lines"] for g in report["groups"].values())
    flagged = sum(g["flagged"] for g in report["groups"].values())
    out += [f"{n} spoken lines from {len(report['speakers'])} speakers. {flagged} lines carry "
            f"at least one finding; {epi} carry an epigram shape.", ""]
    out += ["## Worst lines by score", "",
            "Score is the sum of finding weights (epigram shapes and antithesis 2 to 3, "
            "knowledge leaks and never-words 3, register and length 1).", "",
            "| # | Score | Speaker | Where | Line | Reasons |", "|-:|-:|:-|:-|:-|:-|"]
    for i, d in enumerate(dialogue.worst(report, worst_n), 1):
        where = f"{d['file']}:{d['line']}"
        out.append(f"| {i} | {d['score']} | {d['speaker']} | {_cell(where, 60)} | "
                   f"{_cell(d['text'])} | {_cell(_reasons(d), 300)} |")
    att = report["attribution"]
    out += ["", "## Distinctiveness per character", ""]
    if att["chance"]:
        out += [f"Blind attribution: a complement naive Bayes classifier trained on the other "
                f"{att['folds'] - 1} of {att['folds']} folds names the speaker of each held-out "
                f"line, among {att['speakers_scored']} speakers with {att['min_lines']} or more "
                f"lines. Chance is {att['chance']:.3f}. Intervals are Wilson 95%. The 5-line "
                f"column scores blocks of {att['block_size']} held-out lines at once. A score "
                f"near chance means the voice is generic.", ""]
    out += ["| Speaker | Lines | Per line | 95% interval | x chance | 5-line | Epigram lines |",
            "|:-|-:|-:|:-|-:|-:|-:|"]
    rows = [(s, v) for s, v in report["speakers"].items() if v.get("distinctiveness")]
    rows.sort(key=lambda kv: -kv[1]["distinctiveness"]["accuracy"])
    for name, v in rows:
        d = v["distinctiveness"]
        lift = d["accuracy"] / att["chance"] if att["chance"] else 0
        blk = f"{d['block']['accuracy']:.2f}" if d.get("block") else "-"
        out.append(f"| {name} | {v['lines']} | {d['accuracy']:.2f} | "
                   f"{d['interval'][0]:.2f} to {d['interval'][1]:.2f} | {lift:.1f} | {blk} | "
                   f"{v['epigram_lines']} |")
    out += ["", "## Epigram-flagged lines per group", "",
            "| Group | Lines | Epigram lines | Share | Any finding |", "|:-|-:|-:|-:|-:|"]
    for g, v in report["groups"].items():
        share = v["epigram_lines"] / v["lines"] if v["lines"] else 0
        out.append(f"| {g} | {v['lines']} | {v['epigram_lines']} | {share:.1%} | {v['flagged']} |")
    out += ["", "## Findings by check", "", "| Check | Lines |", "|:-|-:|"]
    for c, k in sorted(report["checks"].items(), key=lambda kv: -kv[1]):
        out.append(f"| {c} | {k} |")
    out += ["", "## Reading these numbers", "",
            "Each hit marks a line to read. A deliberate epigram is still flagged, and a "
            "character can score as distinct through one repeated tic.", ""]
    return "\n".join(out)
