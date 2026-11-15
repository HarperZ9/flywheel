"""benchmark_gateway.py, the gateway overhead section of docs/BENCHMARKS.md.

The numbers come from docs/benchmarks/gateway-overhead.json, which
`scripts/bench_gateway_overhead.py` writes. `benchmark_markdown.py` puts the
lines this module returns into the page, so the page cannot carry a figure
the record does not. The record is one machine's timings: it is not part of
the offline suite seal, and a rerun on another machine gives other numbers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.benchmark_shared import esc, wrap

RECORD = Path(__file__).resolve().parent.parent / "docs" / "benchmarks" / "gateway-overhead.json"
_FORMATS = {"openai": "OpenAI-compatible chat", "anthropic": "Anthropic Messages"}
_SKIP = ("upstream connect", "whole handler", "key debit")
_COMMITS = ("Each call commits two ledger entries to the disk and waits for both: the started "
            "entry before the request leaves, and the end entry before the reply is sent. "
            "Both are in every figure.")


def load_record() -> dict[str, Any]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def _span(values: list[float]) -> str:
    return f"{min(values):.1f} to {max(values):.1f} ms"


def _table(cases: list[dict[str, Any]]) -> list[str]:
    out = ["| interface | upstream format | caller | mode | to first byte, median | "
           "to end, median | to end, p95 | to end, max | of which the two commits, median |",
           "| :-- | :-- | :-- | :-- | --: | --: | --: | --: | --: |"]
    for row in cases:
        total = row["total"]
        out.append(
            f"| `{row['interface']}` | {_FORMATS[row['upstream']]} | "
            f"{'virtual key' if row['caller'] == 'key' else 'gateway token'} | "
            f"{'stream' if row['stream'] else 'plain'} | "
            f"{row['first']['overhead_median_ms']:.2f} | {total['overhead_median_ms']:.2f} | "
            f"{total['overhead_p95_ms']:.1f} | {total['overhead_max_ms']:.1f} | "
            f"{row['commits_median_ms']:.2f} |")
    return out


def _parts(record: dict[str, Any]) -> list[str]:
    plain = next(b for b in record["breakdown"] if not b["stream"])
    named = {label: ms for label, ms in plain["parts_median_ms"].items()
             if not label.startswith(_SKIP)}
    rest = plain["overhead_total_median_ms"] - sum(named.values())
    debit = plain["parts_median_ms"].get("key debit", 0.0)
    out = [wrap(f"For a plain `/v1/messages` call with a virtual key "
                f"({plain['overhead_total_median_ms']:.2f} ms over the stub in that run), the "
                "median time inside each step of the gateway:"), ""]
    out += [f"- {label}: {ms:.2f} ms" for label, ms in named.items()]
    out += ["", wrap(
        "The started entry and the end entry are each one append to the gateway ledger on "
        "disk and one wait for the disk to commit it (fsync). The started entry is "
        "committed before the request leaves the gateway, so a streamed reply's first text "
        "waits for one commit and a plain reply waits for both. "
        f"The key debit is {debit:.2f} ms of the end entry step: a file lock, a read, a "
        f"write and a rename. The remaining {rest:.1f} ms is the two HTTP hops: the "
        "gateway's server accepts the connection, starts a thread and parses the request, "
        "and the gateway opens its own connection to the upstream. A call with the gateway "
        "token has no key lookup and no debit.")]
    return out


def _warm(record: dict[str, Any]) -> list[str]:
    rows = {(r["warm_up"], r["stream"]): r for r in record["key_warm_up"]}
    off, on = rows[(False, False)], rows[(True, False)]
    soff, son = rows[(False, True)], rows[(True, True)]
    return [wrap(
        "After a debit the gateway opens the key list once on a thread of its own "
        "(Windows only). On the measured machine the first open of that file after its "
        "contents change waits about 6 ms, and rewriting the same contents does not show "
        "the wait, which points at real-time file scanning. Before the warm-up that wait "
        "fell on the next call's key check. With the warm-up off, the same run measured "
        f"{off['total_ms']:.2f} ms for a plain call and {soff['first_ms']:.2f} ms to the "
        f"first text of a stream; with it on, {on['total_ms']:.2f} ms and "
        f"{son['first_ms']:.2f} ms. A call that starts within a few milliseconds of the "
        "previous debit still waits. Every check and every debit reads the file as "
        "before.")]


def _lead(record: dict[str, Any]) -> list[str]:
    cases = record["cases"]
    owner = [c["total"]["overhead_median_ms"] for c in cases if c["caller"] == "owner"]
    keyed = [c["total"]["overhead_median_ms"] for c in cases if c["caller"] == "key"]
    commits = [c["commits_median_ms"] for c in cases]
    own = [c["own_total_median_ms"] for c in cases]
    disk = record["disk"]
    return ["## Gateway overhead", "", wrap(
        "What a caller waits for the gateway on one model call to `/v1/messages` and "
        f"`/v1/responses`: a median of {_span(owner)} with the gateway token and "
        f"{_span(keyed)} with a virtual key, to the end of the reply. {_COMMITS} "
        f"The two commits are {_span(commits)} of each figure on the measured disk, and the "
        f"gateway's own work is {_span(own)}. Measured {record['date']} on one machine, "
        "with one client and a loopback stub in place of the provider. Provider network "
        "time is not in these figures. Record: `docs/benchmarks/gateway-overhead.json`."),
        "", *_table(cases), "", wrap(
        "Every figure is milliseconds over the same request sent straight to the stub. For "
        "a stream, the first byte is the first text delta a client can read; it comes after "
        "the started entry's commit. The commit time is the disk's: a bare append and "
        f"commit on the measured disk, with no gateway code, took a median of "
        f"{disk['median_ms']:.2f} ms and {disk['p95_ms']:.2f} ms at the 95th percentile "
        f"over {disk['commits']} commits. On a slower disk the figures grow by twice the "
        "difference. `FLYWHEEL_GATEWAY_LEDGER_SYNC=0` removes the wait and with it the "
        "guarantee that an entry survives a power loss."), ""]


def _method(record: dict[str, Any]) -> list[str]:
    method, box = record["method"], record["machine"]
    cold = [c["first_call_overhead_ms"] for c in record["first_call"]]
    return ["### How it was measured", "", wrap(
        "The same request goes straight to a loopback stub provider and through a real "
        "gateway HTTP server pointed at that stub, in turns, one request at a time. Each "
        "call opens a new connection, since the gateway closes the connection after a "
        f"stream. The stub holds its first byte for {method['stub_delay_ms']:.0f} ms, then "
        f"sends one JSON object or {method['stream_text_events']} text events with no "
        "pause, and notes how long it held each request. That wait is taken out of every "
        "sample. The overhead is the median through the gateway minus the median to the "
        f"stub, over {method['warm_calls']} warm calls after {method['warmup_calls']} "
        "that are thrown away. The p95 and max columns are the gateway's 95th percentile "
        "and slowest call, less the stub's median. The client is Python's `http.client` "
        "and the clock is `time.perf_counter`."), "", wrap(
        f"Machine: {box['cpu']}, {box['logical_cpus']} logical CPUs, {box['ram_gb']} GB "
        f"RAM, {box['os']}, Python {box['python']}."), "",
        "### The first call", "", wrap(
        "The first call after a gateway starts also loads the modules the gateway imports "
        f"on first use. In a fresh process that call took {_span(cold)} more than the "
        "stub. It is not in the table."), ""]


def _tail(record: dict[str, Any]) -> list[str]:
    cases = record["cases"]
    tail = [c["total"]["overhead_p95_ms"] for c in cases]
    alone = max(c["total"]["stub_p95_over_its_median_ms"] for c in cases)
    commits = [c["commits_p95_ms"] for c in cases]
    return [wrap(
        f"The p95 column is {_span(tail)}; the two commits of a call are {_span(commits)} "
        "at their own 95th percentile, so the slow calls are mostly the disk's. Calls sent "
        f"to the stub alone stay within {alone:.1f} ms of their own median at the 95th "
        "percentile. What would lower the figures without giving up the commit before "
        "contact: one commit shared by calls that arrive together (the calls here are "
        "sent one at a time, so it would not show in this table), and a cheaper durable "
        "write on Windows. Neither is built."), ""]


_LEFT_OUT = [
    "- The provider's network time and TLS. The stub is on the loopback interface.",
    "- The system credential store. A virtual key's stored value is read from "
    "memory here; the real read was not timed.",
    "- The first call's module loading, which is reported apart from the table.",
    "- Concurrency. This is a single client sending one request at a time. Other "
    "gateways publish figures at a request rate, and those are not comparable with "
    "these because the conditions differ.",
    "- Connection reuse. Every call opens a new connection to the gateway.",
    "- Any hosted provider, and the Gemini upstream format.",
    "- Other machines, disks and operating systems. One Windows machine with one disk "
    "was measured, and the two commits per call cost what the disk takes.",
    "", "Re-run it:", "", "```bash", "python scripts/bench_gateway_overhead.py",
    "python scripts/build_benchmark_page.py", "```", ""]


def render_markdown(record: dict[str, Any] | None = None) -> list[str]:
    """The section as markdown lines, ending with a blank line."""
    record = load_record() if record is None else record
    return [*_lead(record), *_method(record), "### Where the time goes", "",
            *_parts(record), "", *_tail(record), "### The key list warm-up", "",
            *_warm(record), "", "### What these figures leave out", "", *_LEFT_OUT]


_HEAD = ("interface", "upstream format", "caller", "mode", "to first byte, median",
         "to end, median", "to end, p95", "to end, max", "of which the two commits, median")


def _row_html(row: dict[str, Any]) -> str:
    total = row["total"]
    cells = (f"<code>{esc(row['interface'])}</code>", esc(_FORMATS[row["upstream"]]),
             "virtual key" if row["caller"] == "key" else "gateway token",
             "stream" if row["stream"] else "plain",
             f"{row['first']['overhead_median_ms']:.2f}", f"{total['overhead_median_ms']:.2f}",
             f"{total['overhead_p95_ms']:.1f}", f"{total['overhead_max_ms']:.1f}",
             f"{row['commits_median_ms']:.2f}")
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def section_html(record: dict[str, Any] | None = None) -> str:
    """The section for site/benchmarks.html: the same record, lead and table.

    The method, the breakdown and the slow calls stay in docs/BENCHMARKS.md;
    this section says so, and it lists what the figures leave out in full.
    """
    record = load_record() if record is None else record
    cases = record["cases"]
    owner = [c["total"]["overhead_median_ms"] for c in cases if c["caller"] == "owner"]
    keyed = [c["total"]["overhead_median_ms"] for c in cases if c["caller"] == "key"]
    commits = [c["commits_median_ms"] for c in cases]
    left_out = "".join(f"<li>{esc(line[2:])}</li>" for line in _LEFT_OUT if line.startswith("- "))
    return (
        '<section id="gateway"><h2>Gateway overhead</h2>'
        '<p class="lede">What a caller waits for the gateway on one model call to '
        "<code>/v1/messages</code> "
        f"and <code>/v1/responses</code>: a median of {_span(owner)} with the gateway token and "
        f"{_span(keyed)} with a virtual key, to the end of the reply. {esc(_COMMITS)} "
        f"The two commits are {_span(commits)} of each figure on the measured disk. Measured "
        f"{esc(record['date'])} on one machine, with one client and a loopback stub in place of "
        "the provider. Every figure is milliseconds over the same request sent straight to the "
        "stub. Provider network time is not in these figures.</p>"
        '<div class="tablewrap"><table><thead><tr>'
        + "".join(f"<th>{esc(name)}</th>" for name in _HEAD) + "</tr></thead><tbody>"
        + "".join(_row_html(row) for row in cases) + "</tbody></table></div>"
        f'<p class="lede">Left out of these figures:</p><ul class="caveats">{left_out}</ul>'
        '<p class="lede">The method, the time inside each step and the slow calls are in '
        "<code>docs/BENCHMARKS.md</code>. The record is "
        "<code>docs/benchmarks/gateway-overhead.json</code>, and "
        "<code>python scripts/bench_gateway_overhead.py</code> writes it again.</p></section>")
