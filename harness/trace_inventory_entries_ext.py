"""Registry entries for the run root, lane stores and client stores, plus the
locations that hold no trace-derived data (exemptions, each with a reason).

Run-root classes marked `inferred` come from each writer's module docstring
and write sites, read at the current revision; the design's S12 row called
them unknown, and FW-01 is the package that classifies them.
"""
from __future__ import annotations

from .trace_inventory import Exemption, Gap, Protection, Store
from .trace_inventory_entries import DEL_PLAIN, EXPORT, META, NOT_DESIGNED, _plain

S12 = _plain("classified by FW-01; encryption and deletion are not designed in this "
             "round", "7.16")
LANE = _plain("lane-owned; encryption at rest is the lane's own decision", "7.16")
OUTSIDE = Protection("outside-custody", "the client writes it and sweeps it on its own "
                     "schedule; Flywheel only reads it on import", "7.6")
LANE_EXPORT = Gap("export of lane stores is not designed in this round", "7.16")
CLIENT_DELETE = Gap("the client's own store; a deletion report names the client's purge "
                    "command (7.10)", "7.10")


def _run(sid, name, patterns, classes, shape="dir", **kw):
    protection = META if classes and set(classes) <= {"C4", "C5"} else S12
    return Store(sid, name, "run", patterns, classes, protection, EXPORT, NOT_DESIGNED,
                 shape=shape, owner_binding="run-root", evidence="inferred", **kw)


STORES = (
    Store("S8", "Frozen web snapshots", "run", ("snapshots",), ("C1", "C4"),
          _plain("legacy snapshots stay plaintext; capture snapshots move to encrypted "
                 "S8b", "FW-05b"), EXPORT, DEL_PLAIN, owner_binding="run-root",
          note="third-party page bytes, private when the URL carried a token"),
    Store("S9", "Fold index notes", "run", ("fold_index.json",), ("C1", "C8"),
          _plain("notes are addressed by content hash; encrypting them changes the "
                 "recall API", "7.16"), EXPORT, DEL_PLAIN, shape="file",
          owner_binding="run-root", invalidate=True),
    Store("S10", "Legacy agent-run store", "run", ("agent_runs",), ("C1", "C2"),
          _plain("legacy runs from before #184; no writer remains", "FW-07b"), EXPORT,
          DEL_PLAIN, owner_binding="run-root", evidence="inferred"),
    Store("S11", "Trace bench files", "run", ("bench",), ("C1", "C2"),
          _plain("bench tasks move into encrypted private custody", "FW-12a"), EXPORT,
          DEL_PLAIN, owner_binding="run-root",
          retention="overwritten each run (route unwired, F-05)"),
    _run("S12a", "Lesson memory", ("lessons.jsonl",), ("C1", "C8"), shape="file"),
    _run("S12b", "Science run history", ("science",), ("C2", "C4", "C5")),
    _run("S12c", "Eval runs", ("eval",), ("C1", "C2", "C4", "C5")),
    _run("S12d", "Workflow runs", ("workflow_runs",), ("C1", "C2", "C5")),
    _run("S12e", "Subagent fan-in receipts", ("subagents",), ("C4", "C5")),
    _run("S12f", "Plan forge runs", ("forge",), ("C1", "C8")),
    _run("S12g", "Audit runs", ("audit",), ("C2", "C4", "C5")),
    _run("S12h", "Usage receipts", ("usage",), ("C4",)),
    _run("S12i", "Accepted proof envelopes", ("envelopes",), ("C4", "C5")),
    _run("S12j", "Hook registry and fire history", ("hooks",), ("C2", "C4")),
    _run("S12k", "Vulnerability scan history", ("scans",), ("C2", "C4")),
    _run("S12l", "Schedules and their fires", ("schedules",), ("C1", "C4")),
    _run("S12m", "Browser action chains", ("browser",), ("C1", "C4")),
    _run("S12n", "Skill gates", ("skills",), ("C4", "C5")),
    _run("S12o", "Index job files", ("index-router-jobs", "index-workspace-map-jobs.json"),
         ("C4",)),
    _run("S12p", "Run-root artifacts (Bulletin media)", ("artifacts",), ("C1",)),
    _run("S12q", "Worker home without a state root", ("worker-home",), None,
         note="FLYWHEEL_HOME of worker children when no state root is passed; unknown"),
    _run("S12r", "Local serve temporary files", ("tmp",), None,
         note="TMP and TEMP of the local serve lane (serve.py:36-37); transient, unknown"),
    Store("LNm", "mneme lane folder", "lanes", ("mneme",), ("C1", "C5", "C8"), LANE,
          LANE_EXPORT, Gap("mneme erases through its own forget (MN-01)", "MN-01"),
          owner_binding="lane", note="the lane default database lives here"),
    Store("LNc", "canon lane folder", "lanes", ("canon",), None, LANE, LANE_EXPORT,
          Gap("canon purges through its own context purge (CA-01)", "CA-01"),
          owner_binding="lane", note="authored blocks; trace content unknown"),
    Store("L4", "forum lane folder", "lanes", ("forum",), None, LANE, LANE_EXPORT,
          NOT_DESIGNED, owner_binding="lane",
          note="forum ledger contents unknown until experiment X17"),
    Store("L1", "mneme database", "env", ("mneme.db",), ("C1", "C5", "C8"), LANE,
          LANE_EXPORT, Gap("mneme erases through its own forget (MN-01)", "MN-01"),
          shape="file", env=("MNEME_STATE",), owner_binding="lane"),
    Store("L1a", "mneme replay snapshots", "temp", ("mneme-replay-*.db",),
          ("C1", "C5", "C8"), LANE, LANE_EXPORT,
          Gap("MN-01 moves snapshots to a per-user directory and removes them", "MN-01"),
          shape="file", owner_binding="lane",
          retention="removed best effort at close; a crash leaves the copy"),
    Store("L2", "canon context database", "env", ("canon-context.db",), ("C1", "C4", "C5"),
          LANE, LANE_EXPORT, Gap("canon purges through its own context purge (CA-01)",
                                 "CA-01"), shape="file",
          env=("CANON_CONTEXT_DB", "FLYWHEEL_CANON_CONTEXT_DB"), owner_binding="lane"),
    Store("L3", "relay saved sessions", "env", ("sessions",), ("C1", "C2"), LANE,
          LANE_EXPORT, NOT_DESIGNED, env=("RELAY_SESSION_DIR",), owner_binding="lane"),
    Store("E1", "Claude Code transcripts", "client", ("projects/*/*.jsonl",),
          ("C1", "C2", "C3", "C4"), OUTSIDE,
          Gap("import copies transcripts into custody", "FW-10a"), CLIENT_DELETE,
          env=("CLAUDE_CONFIG_DIR",), owner_binding="client",
          retention="swept by Claude Code after cleanupPeriodDays (default 30)"),
    Store("E2", "Codex rollouts", "client",
          ("sessions/**/rollout-*.jsonl*", "archived_sessions/rollout-*.jsonl*"),
          ("C1", "C2", "C3", "C4"), OUTSIDE,
          Gap("import copies rollouts into custody", "FW-11"), CLIENT_DELETE,
          env=("CODEX_HOME",), owner_binding="client",
          retention="set by Codex; compression and migration are in transition (N-18)"),
)

_NO_TRACE = "holds no trace-derived data"
EXEMPTIONS = (
    Exemption("home", "gateway.token", f"gateway credential; {_NO_TRACE}"),
    Exemption("home", "owner.ref", f"owner identity; {_NO_TRACE}"),
    Exemption("home", "lanes.json", f"lane install registry; {_NO_TRACE}"),
    Exemption("home", "plugins.json", f"plugin configuration; {_NO_TRACE}"),
    Exemption("home", "projects.json", f"project roots; {_NO_TRACE}"),
    Exemption("home", "catalog.json", f"marketplace catalog; {_NO_TRACE}"),
    Exemption("home", "desktop.json", f"desktop UI settings; {_NO_TRACE}"),
    Exemption("home", "connection.json", f"desktop connection settings; {_NO_TRACE}"),
    Exemption("home", "keys", f"receipt signing keys; {_NO_TRACE}"),
    Exemption("home", "state", "container; its entries are registered one by one"),
    Exemption("home", "lanes", "container; its entries are registered one by one"),
    Exemption("home", "run", "the default run root; its entries are registered one by one"),
    Exemption("state", "credential-handles",
              f"opaque handles; secrets live only in the OS keychain; {_NO_TRACE}"),
    Exemption("state", "credential-locks", f"lock files; {_NO_TRACE}"),
    Exemption("run", "router_stats.json", f"per-provider success counts; {_NO_TRACE}"),
    Exemption("run", "packs", f"admitted data-only domain-pack manifests; {_NO_TRACE}"),
    Exemption("run", "runners", f"runner pool membership chain; {_NO_TRACE}"),
    Exemption("run", "hf-cache", f"model download cache of the local serve lane; {_NO_TRACE}"),
    Exemption("run", "pip-cache", f"package cache; {_NO_TRACE}"),
    Exemption("run", "models", f"local model weights; {_NO_TRACE}"),
)

_PER_RUN = "run_root here is a per-run artifact directory the caller names, not the run root"
STATIC_MODULE_EXEMPTIONS = {
    "harness/e2e_report.py": _PER_RUN,
    "harness/e2e_runner.py": _PER_RUN,
    "harness/cross_harness_cli.py": _PER_RUN,
    "harness/cross_harness_run_seal.py": _PER_RUN,
    "harness/cross_harness_postrun_intent.py": _PER_RUN,
    "harness/local_finalizer_run.py": _PER_RUN,
    "harness/scorecard_rebuild.py": _PER_RUN,
    "harness/gateway_worker_env.py": "home here is the worker's state root or "
                                     "run_root/worker-home, registered as S22 and S12q",
    "harness/sandboxed_runner.py:fw_sandbox_*": "Windows sandbox scratch beside the agent "
        "workspace, outside FLYWHEEL_HOME and the run root; it holds one command's output "
        "and is removed when the command ends",
}
