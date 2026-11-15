"""CLI: name a criterion, point at a subject, watch the center reconcile it — witnessed.

    python -m center reconcile --subject <path> --criterion <criterion.json> [--out cert.json]

The criterion file is the human's authored stance: {"name": "...", "dims": {"<dim>": <weight>, ...}}.
v1 uses StubMind/StubJudge so it runs with no model/network; the live engine organs swap in behind the
Mind/Judge interfaces. The subject is rendered into two perceptible channels (text + a structural view)
so two differently-perceiving minds genuinely have different access.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .criterion import CriterionSpec
from .minds import StubMind
from .judge import StubJudge
from .loop import reconcile_at_center


def _views(text: str) -> dict[str, str]:
    """Render the subject into two perceptible forms: the prose, and a structural summary."""
    lines = text.splitlines()
    heads = [ln.strip() for ln in lines if ln.lstrip().startswith(("#", "-", "*", "def ", "class "))][:20]
    structural = f"{len(lines)} lines, {len(text.split())} words; structure: " + " | ".join(heads)
    return {"text": text, "diagram": structural}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="center", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reconcile", help="reconcile a subject toward its telos under a named criterion")
    r.add_argument("--subject", required=True, type=Path)
    r.add_argument("--criterion", required=True, type=Path, help="JSON: {name, dims}")
    r.add_argument("--out", type=Path, default=None, help="write the Certificate JSON here")
    args = ap.parse_args(argv)

    try:
        subject_text = args.subject.read_text(encoding="utf-8")
    except OSError as e:
        print(f"cannot read subject: {e}", file=sys.stderr)
        return 2
    try:
        crit = CriterionSpec.from_dict(json.loads(args.criterion.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"cannot read criterion: {e}", file=sys.stderr)
        return 2

    minds = [StubMind("mind-A", "text"), StubMind("mind-B", "diagram")]
    cert = reconcile_at_center(_views(subject_text), minds, crit, StubJudge())

    print(f"criterion: {crit.name}  ->  verdict: {cert.verdict.value}")
    if cert.winner:
        print(f"winner: {cert.winner}  (weighted {cert.scores[cert.winner]['weighted']})")
        print("candidates (weighted under this criterion):")
        for label, s in sorted(cert.scores.items(), key=lambda kv: -kv[1]["weighted"]):
            print(f"  {label:24s} {s['weighted']:.4f}")
        print("over-build flags:", dict(cert.evidence).get("over_build_flags"))
    else:
        print("reason:", dict(cert.evidence).get("reason"))
    if args.out:
        args.out.write_text(json.dumps(cert.to_dict(), indent=2), encoding="utf-8")
        print(f"witnessed certificate -> {args.out}")
    return 0 if cert.verdict.value == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
