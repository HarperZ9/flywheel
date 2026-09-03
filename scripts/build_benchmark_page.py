"""Generate the benchmark surface from the sealed record, never by hand.

Reads docs/benchmarks/report.json and the live parity matrix and writes two
things: site/benchmarks.html, the published page, and docs/BENCHMARKS.md, the
same content as text. Every number on both comes out of the record, so a page
that disagrees with the run is not possible by transcription error, only by
forgetting to regenerate, and a test catches that.

    python scripts/run_offline_benchmarks.py     # measure, seal
    python scripts/build_benchmark_page.py       # render the seal

Nothing here scores anything. If a number is missing from the record it is
missing from the page, and the five suites that need a live endpoint appear
as named nulls rather than as blanks a reader has to interpret.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent
RECORD = REPO / "docs" / "benchmarks" / "report.json"

from scripts.benchmark_shared import CELL, lede


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _pct(value: Any) -> str:
    return f"{value:.0%}" if isinstance(value, float) and value <= 1 else str(value)


def _headline_number(suite: dict[str, Any]) -> tuple[str, bool]:
    """The one number a card leads with, and whether it reads as a null."""
    head = suite["headline"]
    if "delta_points" in head:
        # A regression inside the noise. It leads with its own number and is
        # drawn as a null, never in the color that means a measured pass.
        return f"{head['delta_points'] * 100:+.2f} pp", True
    for key in ("pass_rate", "recovery_success_rate", "harness_overall"):
        if key in head:
            return _pct(head[key]), head[key] == 0
    first = next(iter(head.values()))
    return str(first), False


def _cards(report: dict[str, Any]) -> str:
    out = []
    for suite in report["suites"]:
        big, is_null = _headline_number(suite)
        rows = "".join(
            f"<div><dt>{_esc(k)}</dt><dd>{_esc(v)}</dd></div>"
            for k, v in suite["headline"].items())
        # A number whose caveats are in the record and not on the page is a
        # number presented as cleaner than it is.
        caveats = "".join(f"<li>{_esc(c)}</li>"
                          for c in suite.get("caveats", ()))
        out.append(
            f'<article class="card"><h3>{_esc(suite["name"])}</h3>'
            f'<p class="big{" null" if is_null else ""}">{_esc(big)}</p>'
            f'<p class="q">{_esc(suite["question"])}</p>'
            f"<dl>{rows}</dl>"
            + (f'<ul class="caveats">{caveats}</ul>' if caveats else "")
            + "</article>")
    return f'<div class="cards">{"".join(out)}</div>'


def _bars(report: dict[str, Any]) -> str:
    """The accountability dimensions, harness against the strawman.

    The strawman is a system with no receipts. It is drawn on the same axis
    because a full bar on its own proves nothing: the benchmark is only
    measuring something if the thing designed to fail here fails here.
    """
    suite = next(s for s in report["suites"] if s["name"] == "accountability")
    rows = []
    for dim in suite["detail"]:
        straw = dim.get("strawman")
        if straw is None:
            # The strawman never scored this axis. An empty track labelled as
            # unscored is the honest drawing; a zero bar would claim it failed.
            second = ('<span class="track"><span class="val unmeasured">'
                      "strawman not scored</span></span>")
        else:
            second = (f'<span class="track"><span class="fill straw" '
                      f'style="width:{straw * 100:.0f}%"></span>'
                      f'<span class="val">strawman {straw:.0%}</span></span>')
        rows.append(
            f'<div class="bar"><span class="name">{_esc(dim["name"])}</span>'
            f'<span class="pair"><span class="track"><span class="fill" '
            f'style="width:{dim["score"] * 100:.0f}%">'
            f'<span class="val">harness {dim["score"]:.0%}</span></span>'
            f"</span>{second}</span></div>")
    head = suite["headline"]
    return (f'<div class="bars">{"".join(rows)}</div>'
            f'<p class="legend">harness {head["harness_overall"]:.0%} against '
            f'strawman {head["strawman_overall"]:.0%} over '
            f'{head["dimensions"]} dimensions. {_esc(suite["non_goal"])}.</p>')


def _matrix(doc: dict[str, Any]) -> str:
    unique = set(doc["summary"]["uniquely_witnessed"])
    rows = []
    for row in doc["rows"]:
        verdict = row["flywheel"]
        cls = "yes" if verdict == "WITNESSED" else "absent"
        mark = " &lowast;" if row["key"] in unique else ""
        cells = "".join(
            f'<td class="cell {CELL[row["competitors"][n]][0]}">'
            f'{CELL[row["competitors"][n]][1]}</td>'
            for n in ("codex", "cursor", "claude-code"))
        rows.append(
            f'<tr><td class="key">{_esc(row["key"])}{mark}</td>'
            f'<td class="desc">{_esc(row["desc"])}</td>'
            f'<td class="cell {cls}">{_esc(verdict.lower())}</td>{cells}</tr>')
    s = doc["summary"]
    return (
        '<div class="tablewrap"><table><thead><tr><th>capability</th>'
        "<th>what it means</th><th>flywheel</th><th>codex</th><th>cursor</th>"
        f'<th>claude code</th></tr></thead><tbody>{"".join(rows)}</tbody>'
        "</table></div>"
        f'<p class="legend">{len(doc["rows"])} rows, {s["witnessed"]} '
        f'witnessed, {s["absent"]} absent, {len(s["uniquely_witnessed"])} '
        "marked &lowast; because no listed peer declares them. The Flywheel "
        "column is checked against this repository every time the matrix is "
        "read, so a row whose witness disappears reports absent. The "
        "competitor columns are dated declarations from public documentation, "
        f'read on {_esc(doc["declared_on"])}, and are not measurements.</p>')


def _nulls(report: dict[str, Any]) -> str:
    items = []
    for entry in report["not_run"]:
        standing = entry.get("standing_result")
        extra = (f'<p class="why">Standing result: {_esc(standing)}</p>'
                 if standing else "")
        items.append(
            f'<div class="null-item"><p class="what">{_esc(entry["suite"])}</p>'
            f'<p class="why">Needs {_esc(entry["needs"])}.</p>{extra}'
            f'<p class="where">{_esc(entry["where"])}</p></div>')
    return f'<div class="nulls">{"".join(items)}</div>'


def render_html(report: dict[str, Any], doc: dict[str, Any]) -> str:
    seal = report["result_sha256"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Flywheel benchmarks</title>
<meta name="description" content="Offline benchmark results, the capability
matrix, and the measurements that were not taken, for the Flywheel engine.">
<link rel="stylesheet" href="assets/benchmarks.css">
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="brand">flywheel<span class="dot">.</span></div>
  <button class="theme" id="themeToggle" aria-label="Switch color theme"><span
    id="themeLabel">theme</span></button>
</header>

<div class="hero">
  <p class="eyebrow">benchmarks &middot; declared {_esc(doc["declared_on"])}</p>
  <h1>Measured, sealed, and re-runnable</h1>
  <p>{lede(report)}</p>
  <p class="seal">seal <span class="hash">{_esc(seal[:32])}</span> &middot;
    python {_esc(report["python"])} &middot; <a href="index.html">back to the
    engine</a></p>
</div>

<section id="suites">
  <h2>What ran</h2>
  <p class="lede">Each card leads with the number that answers its question.</p>
  {_cards(report)}
</section>

<section id="falsifier">
  <h2>The falsifier</h2>
  <p class="lede">A benchmark that everything passes measures nothing. The
    strawman is a system with no receipts, scored on the same axes.</p>
  {_bars(report)}
</section>

<section id="matrix">
  <h2>Against the field</h2>
  <p class="lede">One row per capability. The Flywheel column is a check
    against this repository. The other three are dated readings of public
    documentation and carry no verdict weight.</p>
  {_matrix(doc)}
</section>

<section id="nulls">
  <h2>What was not measured</h2>
  <p class="lede">These need a live model endpoint. They are listed so an
    absent number reads as unmeasured rather than as zero.</p>
  {_nulls(report)}
</section>

<section id="rerun">
  <h2>Re-run it</h2>
  <p>The record is regenerated by one command and the page by a second. A
    test re-runs the first and compares the seal, so the page and the numbers
    cannot drift apart.</p>
  <pre class="cmd">python scripts/run_offline_benchmarks.py
python scripts/build_benchmark_page.py</pre>
</section>

<footer>flywheel &middot; every number on this page came out of
  docs/benchmarks/report.json</footer>
</div>
<script>
(function(){{
  var root=document.documentElement, btn=document.getElementById('themeToggle'),
      lbl=document.getElementById('themeLabel');
  function current(){{
    var t=root.getAttribute('data-theme');
    if(t) return t;
    return matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
  }}
  function apply(t){{ root.setAttribute('data-theme',t);
    if(lbl) lbl.textContent=(t==='dark'?'light':'dark');
    try{{localStorage.setItem('fw-theme',t);}}catch(e){{}} }}
  var saved; try{{saved=localStorage.getItem('fw-theme');}}catch(e){{}}
  apply(saved || current());
  btn.addEventListener('click',function(){{
    apply(current()==='dark'?'light':'dark'); }});
}})();
</script>
</body>
</html>
"""


def build() -> dict[str, str]:
    from harness.parity import parity_matrix

    from scripts.benchmark_markdown import (render_markdown,
                                             render_readme_block, splice_readme)

    report = json.loads(RECORD.read_text(encoding="utf-8"))
    doc = parity_matrix()
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    return {"site/benchmarks.html": render_html(report, doc),
            "docs/BENCHMARKS.md": render_markdown(report, doc),
            # The matrix in machine form. The record seals only its summary
            # counts, so a surface elsewhere that wants the rows has a
            # committed file to read and hash instead of a transcription.
            "docs/benchmarks/parity.json": json.dumps(
                doc, indent=2, sort_keys=True) + "\n",
            # The README keeps everything a person wrote and regenerates only
            # the block between its markers.
            "README.md": splice_readme(readme,
                                       render_readme_block(report, doc))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="fail if a written file is out of date")
    args = ap.parse_args(argv)
    stale = []
    for rel, text in build().items():
        path = REPO / rel
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if args.check:
            if current != text:
                stale.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"{'unchanged' if current == text else 'wrote'} {rel}")
    if stale:
        print("stale, re-run scripts/build_benchmark_page.py: "
              + ", ".join(stale))
        return 1
    if args.check:
        print("benchmark surface matches the record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
