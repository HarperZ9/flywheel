"""Installed-app lane acceptance (PLAN.md WP11): every lane, from an install.

Run it against a folder the Flywheel installer wrote (``<install>/engine/
flywheel-gateway.exe``). It starts the installed engine the way the app does,
under a throwaway profile with a System32-only PATH, in two legs:

1. ``fresh``: a new install with no setup (``FLYWHEEL_GIT=none``). Each lane's
   state must match its class, ``/tools`` must list its main tools with a
   schema, and its main tool must pass its fixture assertion or be refused with
   the named setup item.
2. ``setup``: the same home after each setup step the cards name: Git pointed
   at, the stub model server on 127.0.0.1:8765, the local-model folder chosen
   through its granted route, a canon block placed, a writing draft recorded.

The install folder must not change (lane state lives under the home), the
roster must not move on its own (D1), and the receipt must not hold the token.
The receipt reports each lane's class, or ``BELOW_BAR`` / ``HELD`` with the
failed checks, and states what the run does not prove.

    python scripts/installed_app_lane_acceptance.py --install-root <dir>
        --work <empty dir> --receipt <file.json> [--detail <file>] [--git <git.exe>]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import installed_lane_legs as legs  # noqa: E402
from scripts.installed_lane_cases import CASES, Ctx  # noqa: E402
from scripts.installed_lane_client import Gateway, GrantedCalls  # noqa: E402
from scripts.installed_lane_engine import (  # noqa: E402
    profile_env, start_engine, stop_engine, tree_changes, tree_snapshot)
from scripts.installed_lane_expectations import judge  # noqa: E402
from scripts.installed_lane_verdict import (  # noqa: E402
    DOES_NOT_PROVE, lane_verdict, redact, summary)
from scripts.lane_smoke_fixtures import model_server_answering  # noqa: E402

SCHEMA = "flywheel.installed-app-lane-acceptance/v1"
B_LANES = ("index", "canon", "local-model", "relay", "writing")


def _args(argv):
    p = argparse.ArgumentParser(description="Installed-app lane acceptance (WP11).")
    p.add_argument("--install-root", required=True, type=Path)
    p.add_argument("--work", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    p.add_argument("--detail", type=Path, default=None,
                   help="failed-check bodies (default: <receipt>.detail.json); keep it local")
    p.add_argument("--git", default=shutil.which("git"))
    p.add_argument("--install-mode", default="per-user", choices=("per-user", "all-users"))
    p.add_argument("--stub-port", type=int, default=8765)
    p.add_argument("--meta", action="append", default=[], metavar="KEY=VALUE",
                   help="facts to copy into the receipt, for example source_commit=<sha>")
    return p.parse_args(argv)


def _leg(name: str, install_root: Path, env: dict, ctx: Ctx, host: dict, *,
         stub=None, setup: bool = False) -> dict:
    engine = start_engine(install_root, env)
    secrets = [engine.token]
    try:
        gw = Gateway(engine.base, engine.token)
        calls = GrantedCalls(gw, engine.home, name)
        journey = calls.open_journey()
        steps = _setup_steps(gw, calls, engine.token, ctx) if setup else {}
        guard = legs.settle_and_guard(gw)
        outcomes, detail = legs.run_leg(name, gw, calls, guard["roster"], ctx=ctx,
                                        host=host, stub=stub)
        final = gw.roster()
    finally:
        stop_engine(engine.proc)
    guard.pop("roster")
    return {"journey_status": journey[0], "setup_steps": steps, "guard": guard,
            "outcomes": outcomes, "detail": detail, "secrets": secrets,
            "final_states": {r.get("name"): r.get("state") for r in final.get("lanes", [])}}


def _setup_steps(gw: Gateway, calls: GrantedCalls, token: str, ctx: Ctx) -> dict:
    status, body = calls.set_local_model_root(legs.make_project_folder(ctx))
    steps = {"local_model_root": {"status": status,
                                  "met": isinstance(body, dict) and body.get("met")}}
    steps["writing_draft"] = legs.record_writing_draft(gw, token, ctx)
    steps["checks"] = {lane: calls.check_lane(lane)[0] for lane in B_LANES}
    return steps


def run(ns) -> dict:
    install_root, work = ns.install_root.resolve(), ns.work.resolve()
    exe = install_root / "engine" / "flywheel-gateway.exe"
    if not exe.is_file():
        raise SystemExit(f"no installed engine at {exe}")
    if work.exists() and any(work.iterdir()):
        raise SystemExit("--work must be a new or empty folder")
    ctx = Ctx(home=work / "home", work=work / "profile" / "Documents" / "wp11-fixtures",
              project=work / "profile" / "Documents" / "wp11-project")
    host = {"model_server": model_server_answering(), "git_given": bool(ns.git)}
    host["fixture_repo"] = legs.make_fixture_repo(ctx, ns.git)
    before = tree_snapshot(install_root)
    fresh = _leg("fresh", install_root, profile_env(work, git=None), ctx, host)
    legs.place_canon_block(ctx)
    from scripts.stub_model_server import start_in_thread
    stub = start_in_thread("127.0.0.1", ns.stub_port)
    try:
        setup = _leg("setup", install_root, profile_env(work, git=ns.git), ctx, host,
                     stub=stub, setup=True)
        stub_counts = stub.counts.snapshot()
    finally:
        stub.shutdown()
        stub.server_close()
    changes = tree_changes(before, tree_snapshot(install_root))
    return _receipt(ns, host, fresh, setup, stub_counts, changes)


def _receipt(ns, host, fresh, setup, stub_counts, changes) -> dict:
    lanes = {}
    for lane, case in CASES.items():
        outcomes = {**fresh["outcomes"].get(lane, {}), **setup["outcomes"].get(lane, {})}
        lanes[lane] = lane_verdict(case, outcomes)
    guards = {"fresh_settled": fresh["guard"]["settled"],
              "fresh_d1_unchanged": fresh["guard"]["d1_unchanged"],
              "setup_d1_unchanged": setup["guard"]["d1_unchanged"],
              "install_folder_unchanged": not any(changes.values())}
    body = {"schema": SCHEMA, "install_mode": ns.install_mode,
            "meta": dict(item.split("=", 1) for item in ns.meta if "=" in item),
            "engine_argv": ["flywheel-gateway.exe", "--port", "<free>", "--desktop-launch"],
            "engine_cwd": "the install folder",
            "env_names": sorted(profile_env(Path("x"), git=None)),
            "host": host, "stub_model_server": {"port": ns.stub_port, "counts": stub_counts},
            "summary": summary(lanes, guards), "guards": guards,
            "install_folder_changes": changes,
            "legs": {name: {k: leg[k] for k in ("journey_status", "setup_steps", "guard",
                                                "final_states")}
                     for name, leg in (("fresh", fresh), ("setup", setup))},
            "lanes": lanes, "does_not_prove": list(DOES_NOT_PROVE)}
    detail = {"fresh": fresh["detail"], "setup": setup["detail"]}
    secrets = tuple(fresh["secrets"] + setup["secrets"])
    body, hits = redact(body, secrets)
    detail, detail_hits = redact(detail, secrets)
    body["guards"]["token_absent_from_receipt"] = hits == 0
    body["summary"] = summary(lanes, body["guards"])
    body["expected"] = judge(body["lanes"])
    return {"receipt": body, "detail": detail, "detail_redactions": detail_hits}


def exit_code(receipt: dict) -> int:
    """0 only when every guard held and every lane matched its expected row
    (installed_lane_expectations); BELOW_BAR alone is no longer a green run."""
    expected = receipt.get("expected") or judge(receipt["lanes"])
    return 0 if receipt["summary"]["verdict"] != "FAIL" and expected["matches"] else 1


def main(argv=None) -> int:
    ns = _args(argv)
    out = run(ns)
    ns.receipt.parent.mkdir(parents=True, exist_ok=True)
    ns.receipt.write_text(json.dumps(out["receipt"], indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")
    detail_path = ns.detail or ns.receipt.with_suffix(".detail.json")
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    detail_path.write_text(json.dumps(out["detail"], indent=1, sort_keys=True) + "\n",
                           encoding="utf-8")
    s = out["receipt"]["summary"]
    print(json.dumps({"verdict": s["verdict"], "by_class": s["by_class"],
                      "below_bar": s["below_bar"], "guards_failed": s["guards_failed"],
                      "departures": out["receipt"]["expected"]["departures"]}))
    return exit_code(out["receipt"])


if __name__ == "__main__":
    raise SystemExit(main())
