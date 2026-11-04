"""studyrun command line.

  python -B -m harness.studyrun check   SPEC     spec shape and PREREG anchors, runs nothing
  python -B -m harness.studyrun prereg  SPEC     write PREREG (from spec text), sidecar sha256 and lock
  python -B -m harness.studyrun run     SPEC [--no-ledger]
  python -B -m harness.studyrun check   SPEC --result RESULT.json   also resolve every verdict path on a result
  python -B -m harness.studyrun audit   SPEC [--result RESULT.json] limits, constants and post hoc files, any time

Exit codes: 0 scored (and reproduced, when the spec asks), 2 blocked or bad spec, 3 reproduction mismatch,
4 an autocheck failed (only for specs that declare limits, constants or posthoc, or use studyrun.spec/2).
Run from the repository root.
"""
import argparse
import json
import sys

sys.dont_write_bytecode = True

from . import autocheck, prereg, stage, verdict  # noqa: E402
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


def _print_upgrade(res):
    d = res.get("decision")
    if d is not None:
        print(f"binding: {', '.join(d['binding']) or 'none'}; binding failed: {', '.join(d['binding_fail']) or 'none'}")
        for k, w in d["nonbinding"].items():
            print(f"   non-binding {k}: {w}")
    sc = res.get("forecast_scores")
    if sc:
        from .forecast import ledger_line
        print("forecast: " + ledger_line(sc))
    ac = res.get("autocheck")
    if ac is not None:
        print(f"autocheck ({ac['phase']}): {'ok' if ac['ok'] else 'FAILED'}"
              + (f"; not declared: {', '.join(ac['missing'])}" if ac["missing"] else ""))
        for prob in ac["problems"]:
            print(f"   {prob}")


def _load_result(path):
    return json.loads(open(path, encoding="utf-8").read())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studyrun")
    ap.add_argument("cmd", choices=["check", "prereg", "run", "audit"])
    ap.add_argument("spec")
    ap.add_argument("--no-ledger", action="store_true")
    ap.add_argument("--result", help="result.json for check (path resolution) or audit (value_path constants)")
    a = ap.parse_args(argv)
    try:
        spec = load(a.spec)
        if a.cmd == "check":
            rec, bad = prereg.check(spec)
            out = {"prereg": rec, "problems": bad}
            if a.result:
                out["unresolved_paths"] = [{"verdict": n, "path": p, "why": w}
                                           for n, p, w in verdict.unresolved(_load_result(a.result), spec["verdicts"])]
                bad = bad + out["unresolved_paths"]
            print(json.dumps(out, indent=1, default=str))
            return 2 if bad else 0
        if a.cmd == "audit":
            rep = autocheck.run(spec, "audit", _load_result(a.result) if a.result else None)
            print(json.dumps(rep, indent=1, default=str))
            return 4 if not rep["ok"] else 0
        if a.cmd == "prereg":
            print(json.dumps(prereg.write(spec), indent=1))
            return 0
        res = stage.run(a.spec, append_ledger=not a.no_ledger)
    except (SpecError, prereg.PreregError, stage.Blocked) as e:
        print(f"blocked: {e}", file=sys.stderr)
        return 2
    _print_verdicts(res)
    _print_upgrade(res)
    _print_repro(res["reproduce"])
    if "ledger_number" in res:
        print(f"ledger entry {spec['ledger'].get('prefix', 'F')}{res['ledger_number']} appended to {spec['_ledger_path']}")
    if res["reproduce"] and not res["reproduce"]["all_ok"]:
        return 3
    return 4 if res.get("autocheck") and not res["autocheck"]["ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
