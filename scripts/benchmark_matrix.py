"""benchmark_matrix.py, the capability matrix as HTML.

Split out of `build_benchmark_page.py` when the peer set grew: the table has
one column per peer plus its own legend and source list, so it grows every
time somebody reads another product, while the rest of the page builder does
not. Both renderings of the matrix now sit beside each other, this one and
`render_markdown` in `benchmark_markdown.py`, and neither can quietly print a
cell value the other does not know about because `CELL` is shared.

Nothing here decides anything. The star, the counts, and the four cell values
are computed in `harness/parity.py` and arrive already settled.
"""

from __future__ import annotations

from typing import Any

from scripts.benchmark_shared import CELL, esc, unread_note


def _row_html(row: dict[str, Any], peers: list[dict[str, Any]],
              unique: set[str]) -> str:
    verdict = row["flywheel"]
    cls = "yes" if verdict == "WITNESSED" else "absent"
    mark = " &lowast;" if row["key"] in unique else ""
    cells = "".join(
        f'<td class="cell {CELL[row["competitors"][p["key"]]][0]}">'
        f'{CELL[row["competitors"][p["key"]]][1]}</td>'
        for p in peers)
    return (f'<tr><td class="key">{esc(row["key"])}{mark}</td>'
            f'<td class="desc">{esc(row["desc"])}</td>'
            f'<td class="cell {cls}">{esc(verdict.lower())}</td>{cells}</tr>')


def _legend(doc: dict[str, Any], peers: list[dict[str, Any]]) -> str:
    s = doc["summary"]
    return (f'<p class="legend">{len(doc["rows"])} rows, {s["witnessed"]} '
            f'witnessed, {s["absent"]} absent, {len(s["uniquely_witnessed"])} '
            f"marked &lowast; because all {len(peers)} peers were read on that "
            f"row and none declares it. "
            f"{unread_note(s, len(doc['rows']), ', drawn as <i>unread</i>')} "
            "The Flywheel column is checked against this repository every "
            "time the "
            "matrix is read, so a row whose witness disappears reports absent. "
            "The peer columns are dated readings of public documentation and "
            "public source, and are not measurements.</p>")


def matrix_html(doc: dict[str, Any]) -> str:
    """The table, the per-peer read dates, and the legend under it."""
    unique = set(doc["summary"]["uniquely_witnessed"])
    peers = doc["peers"]
    rows = "".join(_row_html(row, peers, unique) for row in doc["rows"])
    heads = "".join(f"<th>{esc(p['label'])}</th>" for p in peers)
    # Every column says when it was read, next to the column, because one
    # date over five peers hides which of them is the stale one.
    sources = "".join(
        f'<li><b>{esc(p["label"])}</b> read {esc(p["read_on"])}, '
        f'{esc(p["source"])}</li>' for p in peers)
    return ('<div class="tablewrap"><table><thead><tr><th>capability</th>'
            f"<th>what it means</th><th>flywheel</th>{heads}"
            f'</tr></thead><tbody>{rows}</tbody></table></div>'
            f'<ul class="sources">{sources}</ul>{_legend(doc, peers)}')
