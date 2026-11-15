"""Clone each sealed repo fresh and run its own verifier plus a plain sha256sum check.

Usage:
  python watch.py check  --leg NAME --autocrlf true|false [--only OWNER/REPO]
  python watch.py tamper --leg NAME [--only OWNER/REPO]
  python watch.py report RESULTS_DIR

Standard library only. Results land in results/<repo>--<leg>--<mode>.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def load_targets(only: str | None) -> list[dict]:
    targets = json.loads((HERE / "targets.json").read_text(encoding="utf-8"))["targets"]
    if only:
        targets = [t for t in targets if t["repo"] == only]
        if not targets:
            raise SystemExit(f"no target named {only}")
    return targets


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace")
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def clone(repo: str, autocrlf: str, dest: Path) -> str:
    url = f"https://github.com/{repo}.git"
    code, out = run(["git", "clone", "--quiet", "--depth", "1", "-c",
                     f"core.autocrlf={autocrlf}", url, str(dest)], HERE)
    if code != 0:
        raise RuntimeError(f"clone of {repo} failed: {out}")
    return run(["git", "rev-parse", "HEAD"], dest)[1]


def recount(root: Path, manifest: str) -> dict:
    """Compare stored digests with the bytes on disk, tolerating a CRLF manifest."""
    ok = differ = missing = 0
    for raw in (root / manifest).read_bytes().splitlines():
        line = raw.decode("utf-8").rstrip("\r")
        if not line:
            continue
        digest, _, rel = line.partition("  ")
        path = root / rel
        if not path.is_file():
            missing += 1
        elif hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            ok += 1
        else:
            differ += 1
    return {"ok": ok, "differ": differ, "missing": missing, "total": ok + differ + missing}


def sha256sum_check(root: Path, manifest: str) -> dict:
    exe = shutil.which("sha256sum")
    if exe is None:
        raise RuntimeError("sha256sum not found on PATH")
    code, out = run([exe, "--strict", "-c", manifest], root)
    return {"exit": code, "ok_lines": out.count(": OK"), "tail": out.splitlines()[-3:]}


def verifier_check(root: Path, cmd: list[str]) -> dict:
    exe = [sys.executable if cmd[0] == "python" else cmd[0], *cmd[1:]]
    code, out = run(exe, root)
    return {"exit": code, "tail": out.splitlines()[-3:]}


def probe(target: dict, root: Path) -> dict:
    verifier = verifier_check(root, target["verifier"])
    plain = sha256sum_check(root, target["manifest"])
    passed = verifier["exit"] == 0 and plain["exit"] == 0
    return {"verifier": verifier, "sha256sum": plain,
            "recount": recount(root, target["manifest"]), "passed": passed}


def judge_check(target: dict, leg: str, result: dict) -> tuple[bool, str]:
    known = target.get("known_failures", {}).get(leg)
    if result["passed"] and known is None:
        return True, "pass"
    if not result["passed"] and known is not None:
        return True, "expected-fail (known finding)"
    if result["passed"]:
        return False, "known failure no longer reproduces; update targets.json"
    return False, "FAIL"


def do_check(target: dict, leg: str, autocrlf: str, work: Path) -> dict:
    root = work / "clone"
    head = clone(target["repo"], autocrlf, root)
    result = probe(target, root)
    good, verdict = judge_check(target, leg, result)
    note = target.get("known_failures", {}).get(leg, "")
    return {"mode": "check", "head": head, "autocrlf": autocrlf, "good": good,
            "verdict": verdict, "note": note, **result}


def do_tamper(target: dict, leg: str, work: Path) -> dict:
    """Control run on an untouched clone must pass; one changed byte must then fail."""
    root = work / "clone"
    head = clone(target["repo"], "false", root)
    control = probe(target, root)
    victim = root / target["tamper"]
    data = bytearray(victim.read_bytes())
    data[0] ^= 0x01
    victim.write_bytes(bytes(data))
    tampered = probe(target, root)
    bit = tampered["verifier"]["exit"] != 0 and tampered["sha256sum"]["exit"] != 0
    good = control["passed"] and bit
    verdict = "watcher bites" if good else "SELF-TEST FAILED"
    return {"mode": "tamper", "head": head, "autocrlf": "false", "good": good,
            "verdict": verdict, "note": f"flipped one bit in {target['tamper']}",
            "control": control, "tampered": tampered,
            "passed": control["passed"] and not tampered["passed"]}


def row(repo: str, leg: str, res: dict) -> str:
    rc = res.get("recount") or res.get("tampered", {}).get("recount", {})
    counts = f"{rc.get('ok', '?')}/{rc.get('total', '?')}"
    return (f"| {repo} | {leg} | {res['mode']} | {res['head'][:7]} | {counts} | "
            f"{res['verdict']} | {res['note']} |")


HEADER = ("| Repo | Leg | Mode | Head | Digests OK | Result | Note |\n"
          "|:--|:--|:--|:--|:--|:--|:--|")


def emit(lines: list[str]) -> None:
    text = "\n".join([HEADER, *lines]) + "\n"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)


def run_targets(args: argparse.Namespace) -> int:
    RESULTS.mkdir(exist_ok=True)
    lines, failures = [], 0
    for target in load_targets(args.only):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            if args.mode == "check":
                res = do_check(target, args.leg, args.autocrlf, Path(tmp))
            else:
                res = do_tamper(target, args.leg, Path(tmp))
        name = target["repo"].split("/")[1]
        res["repo"], res["leg"] = target["repo"], args.leg
        out = RESULTS / f"{name}--{args.leg}--{args.mode}.json"
        out.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        lines.append(row(name, args.leg, res))
        failures += 0 if res["good"] else 1
    emit(lines)
    return 1 if failures else 0


def report(directory: Path) -> int:
    results = [json.loads(p.read_text(encoding="utf-8"))
               for p in sorted(directory.rglob("*.json"))]
    if not results:
        print("no results found")
        return 1
    emit([row(r["repo"].split("/")[1], r["leg"], r) for r in results])
    return 0 if all(r["good"] for r in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    check = sub.add_parser("check")
    check.add_argument("--leg", required=True)
    check.add_argument("--autocrlf", choices=["true", "false"], required=True)
    check.add_argument("--only")
    tamper = sub.add_parser("tamper")
    tamper.add_argument("--leg", required=True)
    tamper.add_argument("--only")
    rep = sub.add_parser("report")
    rep.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.mode == "report":
        return report(args.directory)
    return run_targets(args)


if __name__ == "__main__":
    raise SystemExit(main())
