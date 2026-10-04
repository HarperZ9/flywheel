"""Registry entries for the run root, lane stores and client stores, plus the
locations that hold no trace-derived data (exemptions, each with a reason).

Run-root classes marked `inferred` come from each writer's module docstring
and write sites, read at the current revision; the design's S12 row called
them unknown, and FW-01 is the package that classifies them.
"""
from __future__ import annotations

from .trace_inventory import Exemption, Gap, Protection, Store
from .trace_inventory_entries import APPLY, EXPORT, META, NOT_DESIGNED, _plain

S12 = _plain("classified by FW-01; encryption and deletion are not designed in this "
             "round", "7.16")
LANE = _plain("lane-owned; encryption at rest is the lane's own decision", "7.16")
OUTSIDE = Protection("outside-custody", "the client writes it and sweeps it on its own "
                     "schedule; Flywheel only reads it on import", "7.6")
LANE_EXPORT = Gap("export of lane stores is not designed in this round", "7.16")
#: What the pinned lane releases delete (lanes_registry pins; test_trace_status_copy
#: fails when a pin moves, so this copy is read again with it).
MNEME_DELETE = Gap("flywheel traces delete does not reach it; in the pinned release, "
                   "mneme's forget erases a memory with its source turns and the rows "
                   "derived from them, on a plan and a second call that confirms it; earlier "
                   "audit entries still name the memory by an id derived from its content",
                   "MN-01")
CANON_DELETE = Gap("flywheel traces delete does not reach it; in the pinned release, canon "
                   "purges context records from its own command line; Flywheel never calls "
                   "purge, and the engine starts canon's context server with purge turned "
                   "off", "CA-01")
#: Lane folders without a row of their own (mneme, canon, forum and relay have one).
LANE_FOLDERS = ("accountable-surface", "array", "articulate", "bulletin", "calibrate-pro",
                "chorus", "crucible", "gather", "index", "isomorph", "learn", "local-model",
                "plexus", "raw", "sofer", "telos", "writing")
CLIENT_DELETE = Gap("the client's own store; a deletion report names the file the client "
                    "keeps and how to remove it there (7.10)", "7.10")


def _run(sid, name, patterns, classes, shape="dir", **kw):
    protection = META if classes and set(classes) <= {"C4", "C5"} else S12
    return Store(sid, name, "run", patterns, classes, protection, EXPORT, NOT_DESIGNED,
                 shape=shape, owner_binding="run-root", evidence="inferred", **kw)


STORES = (
    Store("S8", "Frozen web snapshots", "run", ("snapshots",), ("C1", "C4"),
          _plain("legacy snapshots stay plaintext; capture snapshots move to encrypted "
                 "S8b", "FW-05b"), EXPORT,
          Gap("legacy snapshots stay until every store that cites a snapshot hash is "
              "indexed; a deletion report counts the ones it kept (EN-C11)", "7.16"),
          owner_binding="run-root",
          note="third-party page bytes, private when the URL carried a token"),
    Store("S9", "Fold index notes", "run", ("fold_index.json",), ("C1", "C8"),
          _plain("notes are addressed by content hash; encrypting them changes the "
                 "recall API", "7.16"), EXPORT, APPLY, shape="file",
          owner_binding="run-root", invalidate=True),
    Store("S10", "Legacy agent-run store", "run", ("agent_runs",), ("C1", "C2"),
          _plain("legacy runs from before #184; no writer remains", "7.16"), EXPORT,
          APPLY, owner_binding="run-root", evidence="inferred"),
    Store("S11", "Trace bench files", "run", ("bench",), ("C1", "C2"),
          _plain("legacy bench files; no writer remains since the old bench route was "
                 "retired, and tasks are kept encrypted in store BT", "7.16"), EXPORT,
          APPLY, owner_binding="run-root",
          retention="kept until you delete; nothing writes here any more"),
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
          LANE_EXPORT, MNEME_DELETE, owner_binding="lane",
          note="the lane default database lives here"),
    Store("LNc", "canon lane folder", "lanes", ("canon",), None, LANE, LANE_EXPORT,
          CANON_DELETE, owner_binding="lane", note="authored blocks; trace content unknown"),
    Store("L4", "forum lane folder", "lanes", ("forum",), None, LANE, LANE_EXPORT,
          NOT_DESIGNED, owner_binding="lane",
          note="forum ledger contents unknown until experiment X17"),
    # The lanes layer starts every lane child in lanes/<lane> and points its
    # temp and app-data folders there (lane_workdir), so each registered lane
    # can own a folder here; test_trace_inventory_lanes ties this to the registry.
    Store("LNr", "relay lane folder", "lanes", ("relay",), ("C1", "C2"), LANE,
          LANE_EXPORT, NOT_DESIGNED, owner_binding="lane", evidence="inferred",
          note="relay's saved sessions (task text and tool calls) live here, with its "
               "temp and app-data files"),
    Store("LNo", "other lane folders", "lanes", LANE_FOLDERS, None, LANE, LANE_EXPORT,
          NOT_DESIGNED, owner_binding="lane", evidence="inferred",
          note="each lane's temp and app-data files, plus index's caches and "
               "accountable-surface's receipts and journal; contents unknown"),
    Store("L1", "mneme database", "env", ("mneme.db",), ("C1", "C5", "C8"), LANE,
          LANE_EXPORT, MNEME_DELETE, shape="file", env=("MNEME_STATE",),
          owner_binding="lane"),
    Store("L1a", "mneme replay snapshots left by older releases", "temp",
          ("mneme-replay-*.db",), ("C1", "C5", "C8"), LANE, LANE_EXPORT,
          Gap("not reached by flywheel traces delete; the pinned release keeps its "
              "snapshots in its per-user state folder instead (store L1b)", "MN-01"),
          shape="file", owner_binding="lane",
          retention="older releases removed them best effort at close; a crash left the "
                    "copy"),
    # mneme 0.5.x reads the local app-data folder through the Known Folder API on
    # Windows, and the lanes layer keeps the user's profile for a lane child, so
    # these copies land outside the mneme lane folder on every platform.
    Store("L1b", "mneme replay snapshots", "userstate", ("mneme/snapshots",),
          ("C1", "C5", "C8"), LANE, LANE_EXPORT,
          Gap("not reached by flywheel traces delete; the pinned release removes a "
              "store's snapshots at erase and sweeps the ones whose process is gone", "MN-01"),
          owner_binding="lane", evidence="inferred",
          retention="kept while a replay runs; a crash can leave one until the next sweep",
          note="full copies of the memory database made for a replay, outside the mneme "
               "lane folder"),
    Store("L2", "canon context database", "env", ("canon-context.db",), ("C1", "C4", "C5"),
          LANE, LANE_EXPORT, CANON_DELETE, shape="file",
          env=("CANON_CONTEXT_DB", "FLYWHEEL_CANON_CONTEXT_DB"), owner_binding="lane"),
    Store("L3", "relay saved sessions", "env", ("sessions",), ("C1", "C2"), LANE,
          LANE_EXPORT, NOT_DESIGNED, env=("RELAY_SESSION_DIR",), owner_binding="lane"),
    Store("E1", "Claude Code transcripts", "client", ("projects/*/*.jsonl",),
          ("C1", "C2", "C3", "C4"), OUTSIDE,
          Gap("the client's own store; flywheel traces import copies it into custody "
              "(store IM), which the trace export includes", "7.5"), CLIENT_DELETE,
          env=("CLAUDE_CONFIG_DIR",), owner_binding="client",
          retention="swept by Claude Code after cleanupPeriodDays (default 30)"),
    Store("E2", "Codex rollouts", "client",
          ("sessions/**/rollout-*.jsonl*", "archived_sessions/rollout-*.jsonl*"),
          ("C1", "C2", "C3", "C4"), OUTSIDE,
          Gap("the client's own store; flywheel traces import codex copies it into "
              "custody (store IM), which the trace export includes", "7.5"), CLIENT_DELETE,
          env=("CODEX_HOME",), owner_binding="client",
          retention="set by Codex; compression and migration are in transition (N-18)"),
)

_NO_TRACE = "holds no trace-derived data"
EXEMPTIONS = (
    Exemption("home", "gateway.token", f"gateway credential; {_NO_TRACE}"),
    Exemption("home", "gateway.endpoint*", f"where the running gateway listens; {_NO_TRACE}"),
    Exemption("home", "trace-capture.json", f"capture settings as edited; {_NO_TRACE}"),
    Exemption("home", "trace-retention.json", f"retention policy as edited; {_NO_TRACE}"),
    Exemption("home", ".custody-label-v1", f"marks the custody tree as labeled; {_NO_TRACE}"),
    Exemption("home", "owner.ref", f"owner identity; {_NO_TRACE}"),
    Exemption("home", "lanes.json", f"lane install registry; {_NO_TRACE}"),
    Exemption("home", "node_path", f"the node.exe chosen for the Node lanes, a local path "
              f"and its sha256; {_NO_TRACE}"),
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
    Exemption("state", "custody.lock", f"the custody lock file; {_NO_TRACE}"),
    Exemption("state", "lane-probes.json", f"the engine's own lane checks: outcome, code, "
              f"tool names and the key names a call used; {_NO_TRACE}"),
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
