"""Tool policy data for the evidence lanes: gather, crucible, chorus, articulate,
index, plexus, canon and calibrate-pro.

Plain data, merged into ``lane_tool_policy.LANE_TOOL_POLICY``. Each entry holds
the ``ToolPolicy`` fields that differ from the default (T1, 20 s, no needs,
not main, in the build, effect ``read``). Tool names and order follow each
payload row's ``static_tool_names``. Each reason comes from reading the tool's
code at the pinned tag (the review document names the files).
"""
from __future__ import annotations


def _t(effect: str, reason: str, **fields) -> dict:
    return {"effect": effect, "reason": reason, **fields}


def _main(effect: str, reason: str, **fields) -> dict:
    return _t(effect, reason, main=True, **fields)


def _health(lane: str) -> dict:
    return {f"{lane}.status": _t("read", "Identity and liveness; network-free."),
            f"{lane}.doctor": _t("read", "Readiness report; network-free.")}


_GATHER = {
    **_health("gather"),
    "gather.docs": _main("read", "Reads a local file or folder and returns catalog rows "
                         "and digests; writes nothing.", timeout_s=60),
    "gather.arxiv": _t("network_read", "Fetches arXiv metadata and returns rows; writes "
                       "nothing.", timeout_s=45),
    "gather.federation": _t("read", "Validates or plans a registry in memory. The policy "
                            "review keeps it at T2.", tier="T2"),
    "gather.run": _t("outside_write", "Runs a multi-source config over the network and "
                     "writes the corpus store the config names.", tier="T2", timeout_s=120),
    "gather.context": _main("read", "Reads a corpus and returns bounded excerpts or a "
                            "selection; writes nothing.", timeout_s=60),
    "gather.pilot": _t("outside_write", "Runs, refreshes or bundles a pilot into the "
                       "output folders the caller names.", tier="T2", timeout_s=120),
}

_CRUCIBLE = {
    **_health("crucible"),
    "crucible.assess": _main("read", "Assesses a thesis against measurements in memory "
                             "and returns verdicts.", timeout_s=60),
    "crucible.recheck": _t("read", "Reads a registry and replays a pack the caller "
                           "names; writes nothing."),
    "crucible.recheck_template": _t("read", "Reads a registry assessment and returns a "
                                    "replay template; writes nothing."),
    "crucible.run": _t("outside_write", "Writes the registry, report, packet and bundle "
                       "paths the caller names.", tier="T2", timeout_s=120),
    "crucible.measurement_gate": _t("read", "Checks a packet against criteria."),
    "crucible.review": _t("read", "Validates a review bundle."),
    "crucible.report": _t("read", "Renders a report and returns it. The engine drops "
                          "`out`, which would write a file.", forced_args=(("out", None),)),
    "crucible.batch": _t("outside_write", "Assesses a manifest into the registry the "
                         "caller names.", tier="T2", timeout_s=120),
    "crucible.registry": _t("read", "Lists, verifies or searches a registry. The engine "
                            "forces `apply` false, so prune stays a dry run.",
                            forced_args=(("apply", False),)),
    "crucible.drift": _t("read", "Compares the two latest assessments in a registry."),
    "crucible.refine": _t("outside_write", "Runs the refine loop into the registry the "
                          "caller names.", tier="T2", timeout_s=120),
    "crucible.verdicts": _t("read", "Lists or re-checks assessments in a registry."),
}

_CHORUS = {
    **_health("chorus"),
    "chorus.run": _main("read", "Digests a corpus in memory and returns themes with a "
                        "receipt.", timeout_s=60),
    "chorus.corpora": _t("read", "Lists gather corpora under a folder."),
    "chorus.digests": _t("read", "Lists digests a daemon stored."),
    "chorus.decision": _t("read", "Compares two source packs and returns a review gate."),
}

_ARTICULATE_MODEL = ("Runs the signed-in claude CLI, a model call on the person's account. "
                     "articulate 0.5.0 runs it in a fresh empty folder with settings, MCP "
                     "servers and tools off, from the path the engine passes in "
                     "ARTICULATE_CLAUDE_CLI.")
_ARTICULATE = {
    "check": _main("read", "Local detector; no network."),
    "score": _main("read", "Local score; no network."),
    "judge": _t("spend", _ARTICULATE_MODEL, tier="T2", needs=("claude_cli",), timeout_s=120),
    "fix": _t("spend", _ARTICULATE_MODEL, tier="T2", needs=("claude_cli",), timeout_s=120),
    "polish": _t("spend", _ARTICULATE_MODEL, tier="T2", needs=("claude_cli",), timeout_s=180),
    **_health("articulate"),
}

_ROUTER_JOB = ("Runs on the index lane's long-lived session, so the job's worker outlives the "
               "call that started it; in a frozen engine the worker runs as "
               "--bundled-lane-worker. Job state and caches stay in the lane folder.")
_JOB_READ = _ROUTER_JOB + " The job id must be a plain id."
_INDEX = {
    "index.map": _main("read", "Maps a repository. Needs Git for branch and history. The "
                       "engine drops `resume_state`, which would write a file.",
                       needs=("git",), timeout_s=120, forced_args=(("resume_state", None),)),
    "index.context": _t("read", "Builds a dependency context pack.", timeout_s=120),
    "index.context.envelope": _t("read", "Builds a budgeted context envelope.",
                                 timeout_s=120),
    "index.select": _t("read", "Selects paths with rejection receipts."),
    "index.invalidate": _t("read", "Mints or checks a tree pin and returns it. The policy "
                           "review keeps it at T2.", tier="T2"),
    "index.wiki": _t("read", "Builds or verifies a wiki pack and returns it.",
                     timeout_s=120),
    "index.symbol-graph": _t("read", "Builds a symbol graph for one repo.", timeout_s=60),
    "index.symbol-definition": _main("read", "Finds a symbol's definition from the AST.",
                                     timeout_s=60),
    "index.symbol-references": _main("read", "Finds a symbol's resolved callers.",
                                     timeout_s=60),
    "index.symbol-implementations": _t("read", "Finds subclasses and overrides.",
                                       timeout_s=60),
    **_health("index"),
    "index_graph": _t("read", "Builds a repo dependency graph.", timeout_s=120),
    "index_focus": _t("read", "Returns one repo's dependency neighborhood.", timeout_s=60),
    "index_verify": _t("read", "Grounds a structural claim with file:line evidence.",
                       timeout_s=60),
    "index_router": _t("read", "Builds a workspace map and returns it; its cache stays "
                       "in the lane folder (INDEX_MCP_CACHE_DIR).", timeout_s=120),
    "index_internals": _t("read", "Builds one repo's module graph.", timeout_s=60),
    "index.router.job.start": _t("state_write", _ROUTER_JOB, timeout_s=30),
    "index.router.job.status": _t("read", _JOB_READ),
    "index.router.job.result": _t("read", _JOB_READ, timeout_s=60),
    "index.router.job.cancel": _t("state_write", _JOB_READ),
    "index.router.job.resume": _t("state_write", _JOB_READ, timeout_s=30),
}

_PLEXUS = {
    "plexus_discover": _t("read", "Reads interop manifests and returns the mesh."),
    "plexus_wiring": _t("read", "Returns the capability wiring map."),
    "plexus_plan": _main("read", "Returns the pipeline that feeds a target organ."),
    "plexus_route": _main("read", "Returns the shortest capability path."),
    **_health("plexus"),
}

_CANON = {
    **_health("canon"),
    "canon.blocks": _t("read", "Lists the authored blocks."),
    "canon.render": _t("read", "Returns the rendered region text and writes no file "
                       "(canon's own words). The policy review keeps it at T2.",
                       tier="T2"),
    "canon.validate": _main("read", "Validates one record or the block folder.",
                            needs=("canon_blocks",)),
    "canon.check": _main("read", "Runs the wired check legs over the blocks.",
                         needs=("canon_blocks",)),
}

_CALIBRATE = {
    **_health("calibrate-pro"),
    "calibrate-pro.list-targets": _t("read", "Needs numpy, which the Windows app's "
                                     "catalog slice leaves out.",
                                     not_in_build="numpy_not_in_build"),
    "calibrate-pro.list-panels": _main("read", "Lists the characterized panel catalog."),
    "calibrate-pro.panel-info": _main("read", "Returns one panel's stored "
                                      "characterization."),
}

EVIDENCE_LANE_POLICY: dict[str, dict[str, dict]] = {
    "gather": _GATHER, "crucible": _CRUCIBLE, "chorus": _CHORUS, "articulate": _ARTICULATE,
    "index": _INDEX, "plexus": _PLEXUS, "canon": _CANON, "calibrate-pro": _CALIBRATE,
}
