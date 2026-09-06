"""Re-run every benchmark that needs no model endpoint and no network.

Seven suites qualify. They measure what the harness itself does with a
recorded situation: whether an unaccountable system scores badly on the
accountability axes, whether a governed workflow refuses an action above its
tier, whether an injected fault recovers without a silent failure, whether
state survives a provider swap, whether the source-mined checks still hold
against their datasets, what continued pretraining did to code completion,
and what it costs to keep the receipt. All but the last are deterministic and
offline, so a reader with the repo can re-run this command and get the same
numbers.

The last one is a timing, and a timing is not the same kind of fact. Its
figures come from the disk underneath whoever ran it, so the suite names them
in `unsealed` and the seal leaves them out. What the seal still covers there
is the byte accounting and the verdict, which do not move.

What this does NOT measure is capability. The arms that answer "does the
loop make a model solve more tasks" need a live endpoint, and running this
script does not run them. They are listed in `not_run` with the reason, so a
reader never has to guess whether a missing number was measured and hidden
or simply not measured. The July capability result stands where it was
recorded, uplift unclaimed, interval including zero.

    python scripts/run_offline_benchmarks.py

Writes docs/benchmarks/report.json and prints the headline table. The
committed copy of that file is the published record, and a test re-runs this
and compares, so the page and the numbers cannot drift apart.

The suites themselves are in scripts/offline_suites.py. What is here is the
part that has to stay readable in one sitting: the order, the seal, and what
the seal covers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.offline_suites import NOT_RUN, SUITES  # noqa: E402

SCHEMA = "flywheel.offline-benchmarks/v1"


def _parity() -> dict[str, Any]:
    """The matrix counts, sealed.

    `peers` and `undetermined` are here because `uniquely_witnessed` cannot be
    read without them. That count is "rows every peer was read on and none
    declares", so it moves when the peer set changes and it is only as good as
    how much of that set has actually been read. Sealing the number without
    its denominator and its research debt would let the strongest figure on
    the page travel alone.
    """
    from harness.parity import parity_matrix
    doc = parity_matrix()
    s = doc["summary"]
    return {"declared_on": doc["declared_on"], "rows": len(doc["rows"]),
            "peers": [p["key"] for p in doc["peers"]],
            "witnessed": s["witnessed"], "absent": s["absent"],
            "uniquely_witnessed": len(s["uniquely_witnessed"]),
            "undetermined": len(s["undetermined"]),
            "gaps": list(s["gaps"])}


def _sealable(suite: dict[str, Any]) -> dict[str, Any]:
    """The suite as the seal sees it: the results, without what varies per run.

    How long a suite took is dropped, and so is anything the suite named in
    `unsealed`, whether that names one of its own keys or one number inside
    its headline. A figure that moves with the disk underneath the reader
    would make the seal say nothing at all. The list of dropped names is
    itself sealed, so a later edit that quietly widens it does not hold.
    """
    drop = set(suite.get("unsealed", ()))
    kept = {k: v for k, v in suite.items()
            if k != "seconds" and k not in drop}
    if drop and "headline" in kept:
        kept["headline"] = {k: v for k, v in suite["headline"].items()
                            if k not in drop}
    return kept


def run_all() -> dict[str, Any]:
    suites = []
    for name, question, fn in SUITES:
        started = time.perf_counter()
        result = fn()
        suites.append({"name": name, "question": question,
                       "seconds": round(time.perf_counter() - started, 3),
                       **result})
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "python": platform.python_version(),
        "suites": suites,
        "not_run": NOT_RUN,
        "parity": _parity(),
    }
    report["result_sha256"] = seal(suites, report["parity"])
    return report


def seal(suites: list[dict[str, Any]], parity: dict[str, Any]) -> str:
    """The digest every published benchmark surface is gated on.

    It covers the results and skips the timings, so two runs of the same code
    agree and a changed number cannot ride in unnoticed. This is a function
    rather than four lines inside `run_all` because the test that falsifies it
    has to seal the same way the runner does, and a second copy of the rule is
    a second rule.
    """
    sealed = {"suites": [_sealable(s) for s in suites], "parity": parity}
    return hashlib.sha256(
        json.dumps(sealed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def render_table(report: dict[str, Any]) -> str:
    lines = [f"offline benchmarks  python {report['python']}  "
             f"seal {report['result_sha256'][:16]}"]
    for suite in report["suites"]:
        head = "  ".join(f"{k}={v}" for k, v in suite["headline"].items())
        lines.append(f"  {suite['name']:<24} {head}")
    p = report["parity"]
    lines.append(f"  {'parity':<24} rows={p['rows']}  witnessed={p['witnessed']}"
                 f"  absent={p['absent']}  gaps={len(p['gaps'])}"
                 f"  peers={len(p['peers'])}"
                 f"  undetermined={p['undetermined']}")
    lines.append(f"  not run: {len(report['not_run'])} suites need a live "
                 "endpoint, each named in the report")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/benchmarks",
                    help="directory to write report.json into")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)
    report = run_all()
    print(render_table(report))
    if not args.no_write:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "report.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
