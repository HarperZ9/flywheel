"""The head-to-head section, rendered from the graded metric record.

The offline suites answer what this repository does on its own. They cannot
answer the question a reader actually arrives with, which is whether running a
task through Flywheel beats running it through the harness they already have.
That needs the same tasks put to several harnesses and the answers graded by
the same checkers, which is what `docs/benchmarks/graded-metrics.json` holds.

Two halves, because a reader is buying two different things. Efficiency is what
an attempt cost and how long it took. Quality is what the graded oracles
measured about the answer. A harness that is cheap and wrong is not a bargain,
and a harness that is right and unaffordable is not a product, so neither half
is shown without the other.

Every denominator reaches the page. A role that launched two of seven attempts
says so beside its rate, a cost with partial coverage is drawn as unmeasured
rather than as a total, and a checker that scored attempts and reported no
numbers says that in words. The record already refuses to compute those; this
refuses to draw them.

The section is optional. Before the first head-to-head run there is no record,
and the page says the measurement has not been taken instead of omitting the
question, because a benchmark surface that only shows its wins is an ad.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from harness.attempt_attribution import recovery_sentence, summarize

RECORD = Path(__file__).resolve().parent.parent / "docs" / "benchmarks" / "graded-metrics.json"

ABSENT = "not reported"

# What a null reason means to a reader who will not open the JSON.
REASONS = {
    "provider_cost_unavailable": "this provider states no cost",
    "provider_usage_unavailable": "this provider states no token counts",
    "partial_cost_coverage": "only some attempts reported a cost",
    "no_readable_result": "no attempt came back readable",
}

NOT_RUN = ("No head-to-head run has been recorded yet. The task set, the "
           "adapters, and the graded checkers are in the repository and the "
           "run is one command; until it is run there is no number here, "
           "which is the honest state and not a zero.")


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _cell(value: Any) -> str:
    return ABSENT if value is None else str(value)


def _pct(value: Any) -> str:
    return ABSENT if value is None else f"{value:.0%}"


def _money(value: Any) -> str:
    return ABSENT if value is None else f"${value:.4f}"


def _ms(value: Any) -> str:
    """Seconds once an attempt takes longer than a person waits silently."""
    if value is None:
        return ABSENT
    return f"{value / 1000:.1f} s" if value >= 1000 else f"{value:.0f} ms"


def _reason(role: dict[str, Any], field: str) -> str:
    code = (role.get("null_reasons") or {}).get(field, "")
    return REASONS.get(code, code)


def role_cells(role: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """One role's efficiency, as (label, text, reads_as_null) triples.

    The counted columns carry their own denominator rather than a bare rate,
    because seven attempts at 29 percent and seventy at 29 percent are not the
    same claim and a chart that shows only the rate makes them look identical.
    """
    cost_note = _reason(role, "cost_usd_total")
    return [
        ("launched", f"{role['launched']}/{role['attempts']}", not role["launched"]),
        ("readable", f"{role['scored']}/{role['attempts']}", not role["scored"]),
        ("pass rate", _pct(role["pass_rate"]), role["pass_rate"] is None),
        ("median latency", _ms(role["latency_ms_median"]), role["latency_ms_median"] is None),
        ("cost", _money(role["cost_usd_total"]) if not cost_note else ABSENT, bool(cost_note)),
        ("cost coverage", _pct(role["cost_coverage"]), role["cost_coverage"] is None),
    ]


def _notes(role: dict[str, Any]) -> list[str]:
    """What a reader needs beside the row to read its numbers correctly.

    The readable rate is the number most likely to be misread. A harness that
    answered a task and closed the document with one stray brace scores the
    same as one that never answered, so the reason travels with the rate, and
    so does how many of the refused answers held an answer at all.
    """
    notes = []
    reasons = role.get("unreadable_reasons") or {}
    if reasons:
        notes.append(f"ungraded: {summarize(reasons)}")
    recovered = recovery_sentence(role.get("envelope_recovery"))
    if recovered:
        notes.append(recovered)
    cost = _reason(role, "cost_usd_total") or _reason(role, "cost_usd_per_scored_attempt")
    if cost:
        notes.append(cost)
    return notes


def _efficiency_html(record: dict[str, Any]) -> str:
    head = "".join(f"<th>{_esc(label)}</th>" for label, _, _ in role_cells(record["roles"][0]))
    rows = []
    for role in record["roles"]:
        cells = "".join(
            f'<td class="cell{" unmeasured" if null else ""}">{_esc(text)}</td>'
            for _, text, null in role_cells(role))
        tail = "".join(f'<p class="why">{_esc(note)}.</p>' for note in _notes(role))
        rows.append(f'<tr><td class="key">{_esc(role["provider_role"])}{tail}</td>{cells}</tr>')
    return ('<div class="tablewrap"><table><thead><tr><th>harness</th>'
            f'{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


HATCH_KEY = ("The hatched segment is answers refused at the envelope that held a "
             "complete envelope behind other text. No checker read them, so they are "
             "not readable, and they are not nothing either.")


def _readable_bars(record: dict[str, Any]) -> str:
    """Readable rate per role, with what a refusal hid drawn beside it.

    The width comes from the same two integers as the label rather than from
    the record's own `readable_rate`, so a bar cannot contradict the caption
    printed inside it. A role that launched nothing gets a labelled empty
    track, never a zero-width bar, because a zero bar and an unmeasured one
    look identical at a glance and mean opposite things.

    The hatched segment is where a refusal is opened up. Without it a harness
    that mis-formatted a right answer and a harness that never answered draw
    the same short bar, and the short bar is what a reader remembers.
    """
    rows, hatched = [], False
    for role in record["roles"]:
        attempts = role["attempts"]
        rate = role["scored"] / attempts if attempts else 0
        held = (role.get("envelope_recovery") or {}).get("held_an_envelope") or 0
        share = held / attempts if attempts else 0
        parts = []
        if rate:
            parts.append(f'<span class="fill" style="width:{rate * 100:.0f}%">'
                         f'<span class="val">{role["scored"]}/{attempts}</span></span>')
        if share:
            hatched = True
            parts.append(f'<span class="held" style="left:{rate * 100:.0f}%;'
                         f'width:{share * 100:.0f}%"></span>')
        if not rate:
            # Last, so the label paints over the hatch rather than under it.
            parts.append('<span class="val unmeasured">'
                         f'{_esc(role["scored"])} of {_esc(attempts)} readable</span>')
        rows.append(f'<div class="bar"><span class="name">{_esc(role["provider_role"])}</span>'
                    f'<span class="pair"><span class="track">{"".join(parts)}</span>'
                    "</span></div>")
    key = f'<p class="legend">{HATCH_KEY}</p>' if hatched else ""
    return f'<div class="bars">{"".join(rows)}</div>{key}'


def _checker_html(checker: dict[str, Any]) -> str:
    name = _esc(checker["checker_id"])
    scored = checker["scored_attempts"]
    if not checker["metrics"]:
        return (f'<div class="null-item"><p class="what">{name}</p>'
                f'<p class="why">Scored {scored} attempts and reported no numeric '
                "evidence, so there is nothing to chart for this checker.</p></div>")
    roles = [entry["provider_role"] for entry in checker["metrics"][0]["roles"]]
    head = "".join(f"<th>{_esc(role)}</th>" for role in roles)
    rows = []
    for metric in checker["metrics"]:
        cells = "".join(
            f'<td class="cell{" unmeasured" if entry["mean"] is None else ""}">'
            f'{_esc(_cell(entry["mean"]))}'
            + (f'<span class="n">n={entry["n"]}</span>' if entry["n"] else "")
            + "</td>"
            for entry in metric["roles"])
        rows.append(f'<tr><td class="key">{_esc(metric["metric"])}'
                    f'<span class="n">{_esc(metric["direction"])} is better</span></td>'
                    f"{cells}</tr>")
    return ('<div class="tablewrap"><table><thead><tr>'
            f'<th>{name}</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="legend">{scored} scored attempts. A cell reads '
            f"{ABSENT} when that harness never produced a value for that "
            "metric, which is a different fact from a value of zero.</p>")


def render_html(record: dict[str, Any] | None) -> str:
    """The section body. Never raises on a record that measured nothing."""
    if not record or not record.get("roles"):
        return f'<div class="null-item"><p class="why">{_esc(NOT_RUN)}</p></div>'
    counts = record["counts"]
    parts = [
        f'<p class="legend">{counts["attempts"]} attempts across '
        f'{counts["roles"]} harnesses, {counts["launched"]} launched, '
        f'{counts["scored"]} readable, on task set '
        f'{_esc(", ".join(record["task_set_ids"]) or "unnamed")}.</p>',
        "<h3>What an attempt cost</h3>",
        _efficiency_html(record),
        "<h3>What came back readable</h3>",
        _readable_bars(record),
    ]
    if record["checkers"]:
        parts.append("<h3>What the graded checkers measured</h3>")
        parts += [_checker_html(checker) for checker in record["checkers"]]
    else:
        parts.append('<div class="null-item"><p class="why">No graded checker '
                     "reported on this run, so the quality half of the "
                     "comparison is unmeasured.</p></div>")
    parts.append('<h3>What this does not prove</h3><ul class="caveats">'
                 + "".join(f"<li>{_esc(item)}</li>" for item in record["does_not_prove"])
                 + "</ul>")
    return "".join(parts)


def _markdown_table(header: list[str], rows: list[list[str]]) -> list[str]:
    return (["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
            + ["| " + " | ".join(row) + " |" for row in rows])


def render_markdown(record: dict[str, Any] | None) -> list[str]:
    """The same section as text, for the reader who will not open the page."""
    out = ["## Head to head", ""]
    if not record or not record.get("roles"):
        return out + [NOT_RUN, ""]
    counts = record["counts"]
    out += [f"{counts['attempts']} attempts across {counts['roles']} harnesses, "
            f"{counts['launched']} launched, {counts['scored']} readable, on task set "
            f"{', '.join(record['task_set_ids']) or 'unnamed'}.", "",
            "### What an attempt cost", ""]
    labels = [label for label, _, _ in role_cells(record["roles"][0])]
    out += _markdown_table(
        ["harness", *labels],
        [[role["provider_role"], *[text for _, text, _ in role_cells(role)]]
         for role in record["roles"]])
    stated = [f"- **{role['provider_role']}.** {note[0].upper()}{note[1:]}."
              for role in record["roles"] for note in _notes(role)]
    if stated:
        out += ["", "What the numbers above need beside them:", "", *stated]
    for checker in record["checkers"]:
        out += ["", f"### {checker['checker_id']}", ""]
        if not checker["metrics"]:
            out += [f"Scored {checker['scored_attempts']} attempts and reported no "
                    "numeric evidence, so there is nothing to chart for this checker."]
            continue
        roles = [entry["provider_role"] for entry in checker["metrics"][0]["roles"]]
        out += _markdown_table(
            ["metric", "better", *roles],
            [[metric["metric"], metric["direction"],
              *[_cell(entry["mean"]) for entry in metric["roles"]]]
             for metric in checker["metrics"]])
    out += ["", "### What this does not prove", ""]
    out += [f"- {item}" for item in record["does_not_prove"]]
    return out + [""]


def load_record(path: Path | None = None) -> dict[str, Any] | None:
    """The graded record, or None before the first head-to-head run.

    A missing file is a state the page renders, not an error. A file that is
    there and unreadable is an error, because silently falling back to the
    not-run notice would publish "we never measured this" over a run that
    happened and whose record broke.
    """
    target = Path(path or RECORD)
    if not target.exists():
        return None
    doc = json.loads(target.read_text(encoding="utf-8"))
    if doc.get("schema") != "flywheel.graded_metric_report/v1":
        raise ValueError(f"{target}: not a graded metric report")
    return doc


def section_html(record: dict[str, Any] | None) -> str:
    """The whole section, heading included, ready to splice into the page."""
    return ('<section id="headtohead"><h2>Against the harnesses, on the same tasks</h2>'
            '<p class="lede">One task set, put to every harness the run could reach, '
            "graded by the same checkers. The capability matrix above reads what peers "
            "declare. This runs them.</p>"
            + render_html(record) + "</section>")
