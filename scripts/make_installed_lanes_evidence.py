"""Write the committed summary of one installed-app lane acceptance run.

windows-installed-acceptance.yml uploads one artifact per run: the per-user and
all-users lane receipts, the run summary, the installer checksum and the build
manifest. The release notes and the lane page count their classes from a
summary of the two lane receipts, committed as
project-docs/lanes/evidence/installed-lanes-ci-<run id>.json. This writes it:

    python scripts/make_installed_lanes_evidence.py --run-id RUN --commit SHA \\
        --artifact DIR --from-gh [--update-copy]

It writes nothing and exits 1 when a file is missing, a receipt departs from its
expected row or from packaging/installed-lane-expectations.json, a guard is
missing or false, the two legs disagree on a lane, a receipt, the run summary
or the build manifest names a commit other than --commit, a launch receipt is
incomplete or holds a FAIL, the canon-context or source-stage receipt is not
PASS, the frozen smoke is neither PASS nor BELOW_BAR_EXPECTED, the installer
checksum disagrees with the run summary, the version is not the project's, or a
string in the artifact holds a local path, an e-mail address, a token or an
account name (the runner account, the local user and --deny;
scripts/installed_lanes_privacy.py).

--from-gh reads the job id, the date and the artifact digest with read-only gh
calls, downloads the artifact zip, checks it against that digest and against
DIR (it extracts into DIR when DIR holds no artifact). Without it, pass
--job-id, --date and --artifact-zip-sha256. --update-copy then moves the run
id, commit, date and installer size in the notes, the lane page and the drafts
test (scripts/installed_lanes_copy.py).
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import installed_lanes_gh  # noqa: E402
from scripts.installed_lanes_privacy import private_detail  # noqa: E402

SCHEMA = "flywheel.installed-lanes-ci-evidence-summary/v1"
RECEIPT_SCHEMA = "flywheel.installed-app-lane-acceptance/v1"
RUN_SCHEMA = "flywheel.windows-installed-acceptance-ci/v1"
WORKFLOW = "windows-installed-acceptance.yml"
RUN_SUMMARY = "ci-installed-acceptance-summary.json"
RECEIPTS = "installed-acceptance"
LEGS = {"per-user": "installed-lanes-per-user.json",
        "all-users": "installed-lanes-all-users.json"}
EVIDENCE_DIR = Path("project-docs") / "lanes" / "evidence"
EXPECTATIONS = Path("packaging") / "installed-lane-expectations.json"
RUNNER_ACCOUNT = "runneradmin"
GUARDS = frozenset({"fresh_settled", "fresh_d1_unchanged", "setup_d1_unchanged",
                    "install_folder_unchanged", "token_absent_from_receipt"})
LAUNCH_SCHEMA = "flywheel.installed-launch-acceptance/v1"
LAUNCH = ("installed-launch-full.json", "installed-launch-inspect.json")
CANON = "installed-canon-context.json"
DOES_NOT_PROVE = (
    "A GitHub-hosted Windows Server runner with a System32-only PATH and an administrator "
    "account, not a consumer Windows 11 install; the network was reachable and no host "
    "model server ran.",
    "The run built the source commit named here; a later commit that changes code the "
    "build or the app runs needs its own run.",
    "No provider-backed success, no model quality (a stub model server answers one fixed "
    "word), no bulletin write and no actuation.",
    "One fixture assertion per main tool; the desktop UI was not driven.",
    "A CI build of the source commit, not the installer attached to the release; two "
    "builds of one source tree gave different installer bytes.",
)


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"refused: {path.name} is missing; nothing written")
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def artifact_root(folder: Path) -> Path:
    """The folder that holds the run summary: DIR itself or its one artifact subfolder."""
    if (folder / RUN_SUMMARY).is_file():
        return folder
    found = [p.parent for p in folder.glob(f"*/{RUN_SUMMARY}")]
    if len(found) != 1:
        raise SystemExit(f"{folder}: expected one {RUN_SUMMARY}, found {len(found)}")
    return found[0]


def _lane_key(row: dict) -> tuple:
    return (row["verdict"], row["class_measured"], sorted(f["check"] for f in row["failed"]),
            row["untested"], row["not_measurable"])


def check_leg(mode: str, receipt: dict, commit: str, expected: dict) -> list[str]:
    out = []
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("install_mode") != mode:
        out.append(f"{mode}: schema or install_mode is not a {mode} lane receipt")
    if receipt.get("expected") != {"departures": [], "matches": True}:
        out.append(f"{mode}: expected.matches is not true with no departures")
    guards = receipt.get("guards") or {}
    if set(guards) != GUARDS or not all(value is True for value in guards.values()):
        out.append(f"{mode}: a guard is missing or not true: {guards}")
    summary = receipt.get("summary") or {}
    if summary.get("guards_failed") != []:
        out.append(f"{mode}: summary.guards_failed is not empty")
    if receipt.get("meta", {}).get("source_commit") != commit:
        out.append(f"{mode}: meta.source_commit is not {commit}")
    lanes = receipt.get("lanes") or {}
    if set(lanes) != set(expected):
        out.append(f"{mode}: lanes differ from the expectations file")
    for lane, row in expected.items():
        got = lanes.get(lane)
        if got is None:
            continue
        failed = sorted(f["check"] for f in got["failed"])
        if got["verdict"] != row["verdict"] or failed != sorted(row.get("failed", [])):
            out.append(f"{mode}: {lane} is {got['verdict']} {failed}, expected {row}")
    counted = Counter(r["class_measured"] for r in lanes.values() if r["verdict"] == "AT_CLASS")
    if dict(counted) != summary.get("by_class"):
        out.append(f"{mode}: summary.by_class does not count the AT_CLASS rows")
    return out


def check_run(root: Path, run: dict, commit: str, version: str, engines: set) -> list[str]:
    out = []
    if run.get("schema") != RUN_SCHEMA or run.get("source_commit") != commit:
        out.append(f"{RUN_SUMMARY}: schema or source_commit is not {commit}")
    if run.get("version") != version:
        out.append(f"{RUN_SUMMARY}: version {run.get('version')} is not {version}")
    installer = run.get("installer") or {}
    sums_file = root / "SHA256SUMS.txt"
    sums = sums_file.read_text(encoding="utf-8-sig").split() if sums_file.is_file() else []
    if sums != [installer.get("sha256"), installer.get("name")]:
        out.append("SHA256SUMS.txt does not name the run summary's installer sha256")
    if not isinstance(installer.get("size"), int) or installer["size"] <= 0:
        out.append(f"{RUN_SUMMARY}: installer.size is not a byte count")
    if engines != {run.get("engine_sha256")}:
        out.append(f"engine_sha256 differs between the legs and {RUN_SUMMARY}")
    manifest = root / "installed-build-manifest.json"
    if not manifest.is_file() or read_json(manifest).get("source_commit") != commit:
        out.append(f"installed-build-manifest.json: missing, or source_commit is not {commit}")
    return out


def check_other_receipts(root: Path, commit: str) -> list[str]:
    """The launch, canon-context, source-stage and frozen-smoke receipts."""
    out = []
    for name in LAUNCH:
        got = read_json(root / RECEIPTS / name)
        failed = [a.get("id") for a in got.get("assertions") or [] if a.get("state") == "FAIL"]
        if (got.get("schema") != LAUNCH_SCHEMA or got.get("complete") is not True
                or got.get("source_commit_expected") != commit or failed):
            out.append(f"{name}: not a complete {LAUNCH_SCHEMA} receipt of {commit} "
                       f"without FAIL {failed}")
    canon = read_json(root / RECEIPTS / CANON)
    if (canon.get("source") or {}).get("commit") != commit or canon.get("verdict") != "PASS":
        out.append(f"{CANON}: source.commit is not {commit}, or the verdict is not PASS")
    if read_json(root / "python-lane-source-stage.json").get("verdict") != "PASS":
        out.append("python-lane-source-stage.json: the verdict is not PASS")
    smoke = read_json(root / "frozen-gateway-smoke.json").get("verdict")
    if smoke not in ("PASS", "BELOW_BAR_EXPECTED"):
        out.append(f"frozen-gateway-smoke.json: verdict {smoke}")
    return out


def check_artifact(root: Path, commit: str, expected: dict, version: str,
                   deny: list[str]) -> tuple[list[str], dict, dict]:
    receipts = {m: read_json(root / RECEIPTS / name) for m, name in LEGS.items()}
    run = read_json(root / RUN_SUMMARY)
    problems = [p for m, r in receipts.items() for p in check_leg(m, r, commit, expected)]
    first, other = receipts["per-user"], receipts["all-users"]
    for lane in sorted(set(first["lanes"]) & set(other["lanes"])):
        if _lane_key(first["lanes"][lane]) != _lane_key(other["lanes"][lane]):
            problems.append(f"{lane}: the two legs reached different outcomes")
    if first.get("summary") != other.get("summary"):
        problems.append("the two legs' summaries differ")
    engines = {r.get("meta", {}).get("engine_sha256") for r in receipts.values()}
    problems += check_run(root, run, commit, version, engines)
    problems += check_other_receipts(root, commit)
    problems += private_detail(root, deny)
    return problems, receipts, run


def build_summary(root: Path, receipts: dict, run: dict, meta: dict) -> dict:
    legs = {}
    for mode, name in LEGS.items():
        receipt = receipts[mode]
        raw = (root / RECEIPTS / name).read_bytes()
        legs[mode] = {"receipt": name, "receipt_sha256": hashlib.sha256(raw).hexdigest(),
                      "install_mode": receipt["install_mode"], "summary": receipt["summary"],
                      "guards": receipt["guards"],
                      "model_server": receipt["host"]["model_server"]}
    first = receipts["per-user"]
    lanes = {lane: {"class_plan": row["class_plan"], "class_expected": row["class_expected"],
                    "class_measured": row["class_measured"], "verdict": row["verdict"],
                    "failed_checks": sorted(f["check"] for f in row["failed"]),
                    "untested": row["untested"], "not_measurable": row["not_measurable"]}
             for lane, row in sorted(first["lanes"].items())}
    return {
        "schema": SCHEMA,
        "what": ("Per-lane verdicts from the installed-app lane acceptance in GitHub Actions "
                 f"workflow {WORKFLOW}, run {meta['run_id']} on {meta['date']}, which built "
                 "an installer from the source commit below with the release build steps, "
                 "installed it per user and then for all users on a GitHub-hosted Windows "
                 "Server runner, and ran the lane check against each install. Both legs "
                 "reached the same verdict for every lane."),
        "run": {"workflow": WORKFLOW, "run_id": meta["run_id"], "job_id": meta["job_id"],
                "date": meta["date"], "artifact_zip_sha256": meta["artifact_zip_sha256"]},
        "source_commit": first["meta"]["source_commit"],
        "engine_sha256": first["meta"]["engine_sha256"],
        "installer": {"name": run["installer"]["name"], "bytes": run["installer"]["size"]},
        "legs": legs,
        "summary": first["summary"],
        "guards": {k: all(legs[m]["guards"][k] for m in legs) for k in first["guards"]},
        "lanes": lanes,
        "does_not_prove": list(DOES_NOT_PROVE),
    }


def _args(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", type=int, required=True)
    ap.add_argument("--commit", required=True, help="the source commit, 40 hex")
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--from-gh", action="store_true")
    ap.add_argument("--repo", default="HarperZ9/flywheel")
    ap.add_argument("--job-id", type=int)
    ap.add_argument("--date")
    ap.add_argument("--artifact-zip-sha256")
    ap.add_argument("--deny", action="append", default=[],
                    help="an account or host name that must not appear (repeatable)")
    ap.add_argument("--update-copy", action="store_true")
    ap.add_argument("--root", type=Path, default=REPO)
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        ap.error("--commit must be a full 40-hex commit")
    return args


def _meta(args) -> dict:
    if args.from_gh:
        return installed_lanes_gh.fetch_and_verify(args.repo, args.run_id, args.artifact)
    given = {"job_id": args.job_id, "date": args.date,
             "artifact_zip_sha256": args.artifact_zip_sha256}
    missing = [k for k, v in given.items() if v is None]
    if missing:
        raise SystemExit(f"without --from-gh, pass --{', --'.join(missing)}".replace("_", "-"))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        raise SystemExit("--date must be YYYY-MM-DD")
    if not re.fullmatch(r"[0-9a-f]{64}", args.artifact_zip_sha256):
        raise SystemExit("--artifact-zip-sha256 must be 64 lowercase hex")
    return {"run_id": args.run_id, **given}


def main(argv=None) -> int:
    args = _args(argv)
    meta = _meta(args)
    root = artifact_root(args.artifact)
    expected = read_json(args.root / EXPECTATIONS)["lanes"]
    version = tomllib.loads((args.root / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    deny = [RUNNER_ACCOUNT, getpass.getuser(), *args.deny]
    problems, receipts, run = check_artifact(root, args.commit, expected, version, deny)
    if problems:
        print("\n".join(problems) + f"\nrefused: {len(problems)} problem(s); nothing written")
        return 1
    summary = build_summary(root, receipts, run, meta)
    out = args.root / EVIDENCE_DIR / f"installed-lanes-ci-{args.run_id}.json"
    old_name = None
    if args.update_copy:
        from scripts import installed_lanes_copy
        old_name = installed_lanes_copy.current_evidence(args.root)
        old = json.loads((args.root / EVIDENCE_DIR / old_name).read_text("utf-8"))
        edits = installed_lanes_copy.plan(args.root, old, summary, out.name)
    out.write_bytes((json.dumps(summary, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    print(f"wrote {out.relative_to(args.root).as_posix()}: {len(summary['lanes'])} lanes, "
          f"{summary['summary']['by_class']}, installer {summary['installer']['bytes']} bytes")
    if old_name is not None:
        for line in installed_lanes_copy.apply(args.root, edits):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
