"""studyrun command line.

  python -B -m harness.studyrun check   SPEC     spec shape and PREREG anchors, runs nothing
  python -B -m harness.studyrun prereg  SPEC     write PREREG (from spec text), sidecar sha256 and lock
  python -B -m harness.studyrun run     SPEC [--no-ledger]

Exit codes: 0 scored (and reproduced, when the spec asks), 2 blocked or bad spec, 3 reproduction mismatch.
Run from the repository root.
"""
import argparse
import json
import sys

sys.dont_write_bytecode = True

from . import prereg, stage  # noqa: E402
from .spec import SpecError, load  # noqa: E402


def _print_verdicts(res):
    for name, v in res["verdicts"].items():
        print(f"{name}: {v['verdict']}")
        for r in v["rules"]:
            tag = {True: "holds", False: "fails", None: "untestable"}[r["holds"]]
            print(f"   {r['rule']:<60} {tag}  ({r['left']!r} vs {r['right']!r}){'  ' + r['why'] if r.get('why') else ''}")


def _print_repro(rep):
    if not rep:
        return
    print(f"reproduction against {rep['source']} (tol {rep['tol']}): {'OK' if rep['all_ok'] else 'MISMATCH'}")
    for r in rep["rows"]:
        print(f"   {'ok ' if r['ok'] else 'BAD'} {r['ours']:<46} {r['value']!r:>24}  recorded {r['recorded_value']!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyrun")
    ap.add_argument("cmd", choices=["check", "prereg", "run"])
    ap.add_argument("spec")
    ap.add_argument("--no-ledger", action="store_true")
    a = ap.parse_args(argv)
    try:
        spec = load(a.spec)
        if a.cmd == "check":
            rec, bad = prereg.check(spec)
            print(json.dumps({"prereg": rec, "problems": bad}, indent=1))
            return 2 if bad else 0
        if a.cmd == "prereg":
            print(json.dumps(prereg.write(spec), indent=1))
            return 0
        res = stage.run(a.spec, append_ledger=not a.no_ledger)
    except (SpecError, prereg.PreregError, stage.Blocked) as e:
        print(f"blocked: {e}", file=sys.stderr)
        return 2
    _print_verdicts(res)
    _print_repro(res["reproduce"])
    if "ledger_number" in res:
        print(f"ledger entry {spec['ledger'].get('prefix', 'F')}{res['ledger_number']} appended to {spec['_ledger_path']}")
    return 3 if res["reproduce"] and not res["reproduce"]["all_ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
