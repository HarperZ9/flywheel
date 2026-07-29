#!/usr/bin/env python3
"""render_report.py -- the confirmatory record, rendered and never computed.

The two drivers write endpoint-report.json and arms-report.json, and both are
built unable to run before the journal carries run_end. This renderer turns
their artifacts into one readable record, and it COMPUTES NOTHING: no rate it
does not copy, no interval it does not copy, no comparison of any kind. A
renderer that derives even one number is an analysis tool wearing a formatter's
name, and analysis lives behind the run_end gate, not here.

Three rendering rules come straight from the frozen preregistration:

  * Tables are ordered by rung id and never by size, and no cross-rung delta
    appears anywhere (section 5). The driver artifacts store per-rung maps with
    sorted keys, and this renderer preserves that order rather than re-sorting
    by any quantity.
  * The confounds print inline with EVERY per-rung table, never once in a
    footer a reader may not reach (section 5).
  * The MDE prints next to every comparison including every null, and the
    self-scored comparison prints its REFUSAL rather than being dropped
    (sections 4 and 6).

Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from harness.endpoint import ATTRIBUTIONS, FOUR_WAY                # noqa: E402

ENDPOINT_SCHEMA = "flywheel.endpoint/v1"
ARMS_SCHEMA = "flywheel.pool-arm/v1"


class RenderError(ValueError):
    """A record that cannot be rendered without inventing part of it."""


def _load(path: Path, expect: str) -> dict:
    if not path.is_file():
        raise RenderError(
            f"no {path.name}: the driver has not produced it, and this "
            "renderer does not compute anything in its place")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != expect:
        raise RenderError(
            f"{path.name} carries schema {doc.get('schema')!r}, not {expect!r}; "
            "refusing to render a shape this code does not know")
    return doc


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bullets(items) -> list:
    return [f"- {x}" for x in items]


def _confounds(block: dict) -> list:
    out = ["", "Confounds, inline with this table by design:"]
    out += _bullets(block.get("confounds", []))
    return out


def _primary(fam: str, block: dict) -> list:
    p = block["primary"]
    out = [f"## {fam}: the primary endpoint", "",
           f"> {p['endpoint']}", "",
           f"- certificate bodies in the union: {p['n_bodies']}",
           f"- rung contexts each was submitted in: {len(p['rung_contexts'])}",
           f"- disagreements: {p['n_disagreements']}",
           f"- bodies under multiple instances (reported, not failures): "
           f"{len(p['bodies_under_multiple_instances'])}",
           f"- endpoint met: {p['met']}", "",
           "Does not prove:"]
    out += _bullets(p["does_not_prove"])
    return out


def _secondary(fam: str, block: dict) -> list:
    sec = block["secondary"]
    head = (["rung", "graded", "well-formed"] + list(FOUR_WAY)
            + list(ATTRIBUTIONS))
    out = [f"## {fam}: per-rung verdicts, ordered by rung id, no delta", "",
           "| " + " | ".join(head) + " |",
           "|" + "---|" * len(head)]
    for rung, row in sec["per_rung"].items():
        cells = [rung, str(row["graded_slots"]), str(row["well_formed"])]
        cells += [str(row["verdicts"][v]) for v in FOUR_WAY]
        cells += [str(row["attribution"][a]) for a in ATTRIBUTIONS]
        out.append("| " + " | ".join(cells) + " |")
    out += _confounds(sec)
    excluded = block.get("excluded_tasks") or {}
    out += ["", "Tasks with no candidate in any slot, excluded and named:"]
    out += (_bullets(f"{r}: {', '.join(ts)}" for r, ts in excluded.items())
            or ["- none"])
    out += ["", "Does not prove:"] + _bullets(sec["does_not_prove"])
    return out


def _one_arm(name: str, a: dict) -> str:
    cells = [name, str(a["passes"]), str(a["graded"]), str(a["pass_rate"]),
             f"[{a['wilson_95'][0]}, {a['wilson_95'][1]}]",
             str(a["oracle_calls"]), a["selector"], a["scored_by"]]
    return "| " + " | ".join(cells) + " |"


def _comparison(name: str, c: dict) -> list:
    out = [f"**{c['arm_a']} vs {c['arm_b']}** ({name}): "
           f"n_paired={c['n_paired']}, discordant={c['discordant']}, "
           f"a_only={c['a_only']}, b_only={c['b_only']}, delta={c['delta']}, "
           f"p_exact={c['p_exact']}"]
    if c.get("refused"):
        out.append(f"- REFUSED: {c['refused']}")
    mde = c.get("mde") or {}
    out.append(f"- MDE: {mde.get('note', 'ABSENT, which is itself a defect')}")
    return out


def _arms(fam: str, block: dict, confounds: list) -> list:
    out = [f"## {fam}: arms, offline from the cached pool", "",
           f"- primary checker: `{block['primary_checker']}`",
           f"- held-out checker: `{block['held_out_checker']}`", ""]
    out += _bullets(block.get("family_not_proven", []))
    head = ["arm", "passes", "graded", "pass rate", "wilson 95",
            "oracle calls", "selector", "scored by"]
    for rung, row in block["per_rung"].items():
        out += ["", f"### {fam} @ {rung}", "",
                f"- observed accept rate (placebo matched to it): "
                f"{row['observed_accept_rate']}",
                f"- selection seed {row['selection_seed']}, "
                f"placebo seed {row['placebo_seed']}", "",
                "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        for arm_name, arm in row["arms"].items():
            if arm_name == "pass_at_k":
                continue
            out.append(_one_arm(arm_name, arm))
        curve = row["arms"]["pass_at_k"]["curve"]
        out += ["", "pass@k curve (diagnostic, no claim attached): "
                + ", ".join(f"k={k}: {v['pass_rate']}"
                            for k, v in curve.items()), ""]
        for name, comp in row["comparisons"].items():
            out += _comparison(name, comp) + [""]
        out += ["Does not prove:"] + _bullets(row["does_not_prove"])
        out += ["", "Confounds, inline with this table by design:"]
        out += _bullets(confounds)
    return out


def render(endpoint_doc: dict, arms_doc: dict, provenance: dict) -> str:
    lines = ["# Confirmatory pass: the rendered record", "",
             "Rendered from the driver artifacts named below. This file "
             "computes nothing: every number in it is copied, and anything "
             "not in the artifacts is not in this record.", ""]
    lines += _bullets(f"`{k}` sha256 `{v}`" for k, v in provenance.items())
    lines += ["", f"Pinned criteria: `{json.dumps(endpoint_doc['pinned_criterion_sha256'], sort_keys=True)}`"]
    for fam, block in endpoint_doc["families"].items():
        confounds = block["secondary"].get("confounds", [])
        lines += [""] + _primary(fam, block)
        lines += [""] + _secondary(fam, block)
        arms_block = arms_doc["families"].get(fam)
        if arms_block is None:
            raise RenderError(
                f"the arms report carries no family {fam!r}; rendering the "
                "endpoint without its arms would present half a record as whole")
        lines += [""] + _arms(fam, arms_block, confounds)
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports", default=str(REPO / "artifacts" / "endpoint"))
    ap.add_argument("--out", default=None,
                    help="defaults to confirmatory-report.md beside the inputs")
    args = ap.parse_args(argv)
    reports = Path(args.reports)
    ep, ar = reports / "endpoint-report.json", reports / "arms-report.json"
    try:
        text = render(_load(ep, ENDPOINT_SCHEMA), _load(ar, ARMS_SCHEMA),
                      {ep.name: _sha(ep), ar.name: _sha(ar)})
    except RenderError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    out = Path(args.out) if args.out else reports / "confirmatory-report.md"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"rendered -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
