"""Argument facts for the lane tool policy: path arguments, id arguments, egress.

Plain data, merged into ``lane_tool_policy.LANE_TOOL_POLICY`` over the three
lane-family tables. Each entry names, per tool, from the pinned ``inputSchema``
of that tool (the Phase 3 ``tools/list`` captures and the pinned sources):

- ``path_args``: arguments that name a file or folder the tool reads. On every
  route the engine refuses one that resolves inside the Flywheel home outside
  the lane's own folder (POLICY-DECISION C-14), and an agent run cannot select
  the tool at all until a workspace check confines it (C-12);
- ``id_args``: arguments a lane joins into a file path of its own. Each must be
  a plain id (``lane_tool_policy.ID_PATTERN``, no ``..``), or the call is
  refused before a child spawns (C-4, finding F1: learn joins ``sessionId`` and
  ``runId`` into paths unchecked);
- ``open_egress``: the tool fetches a URL the caller names, an open outbound
  channel an agent run must not hold (C-12, finding F6).

Stated limit: a path inside a nested object or a free-text field escapes a
name-based list, and the write-containment probe measures writes, not reads.
"""
from __future__ import annotations

_TUTOR = ("learn_tutor_plan", "learn_tutor_record", "learn_tutor_mastery",
          "learn_tutor_due", "learn_tutor_studyplan", "learn_tutor_misconceptions",
          "learn_tutor_reverify", "learn_tutor_derive_schedule")
_INDEX_ROOT = ("index.map", "index.context", "index.context.envelope", "index.select",
               "index.invalidate", "index.wiki", "index.symbol-graph",
               "index.symbol-definition", "index.symbol-references",
               "index.symbol-implementations", "index_graph", "index_focus",
               "index_verify", "index_router", "index_internals",
               "index.router.job.start")


def _paths(*names: str) -> dict:
    return {"path_args": tuple(names)}


ARG_POLICY: dict[str, dict[str, dict]] = {
    "gather": {"gather.docs": _paths("path"), "gather.context": _paths("corpus"),
               "gather.federation": _paths("registry"),
               "gather.run": _paths("config_path"),
               "gather.pilot": _paths("manifest", "output", "bundle_output")},
    "crucible": {"crucible.assess": _paths("thesis", "measurements"),
                 "crucible.recheck": _paths("dir", "index", "pack"),
                 "crucible.run": _paths("thesis", "registry", "measurements", "report",
                                        "out", "bundle"),
                 "crucible.measurement_gate": _paths("packet", "criteria"),
                 "crucible.review": _paths("bundle"),
                 "crucible.report": _paths("dir", "index"),
                 "crucible.batch": _paths("manifest", "registry", "reports"),
                 "crucible.registry": _paths("dir"), "crucible.drift": _paths("dir"),
                 "crucible.refine": _paths("config", "thesis", "registry"),
                 "crucible.verdicts": _paths("dir")},
    "chorus": {"chorus.run": _paths("corpus"), "chorus.corpora": _paths("root"),
               "chorus.digests": _paths("store"),
               "chorus.decision": _paths("current", "reference")},
    "index": {name: _paths("root") for name in _INDEX_ROOT},
    "plexus": {name: _paths("dir") for name in (
        "plexus_discover", "plexus_wiring", "plexus_plan", "plexus_route")},
    "mneme": {"mneme.origin_recheck": _paths("allowed_root")},
    "canon": {"canon.validate": _paths("record")},
    "accountable-surface": {
        "accountable-surface.perceive": {"path_args": ("subject",), "open_egress": True},
        "accountable-surface.device_ls": _paths("path")},
    "learn": {**{name: {"id_args": ("sessionId",)} for name in _TUTOR},
              "learn_tutor_reverify": {"id_args": ("sessionId",), "path_args": ("file",)},
              "learn_verify": {"id_args": ("runId",)},
              "learn_receipt": {"id_args": ("runId",)},
              "learn_dry_run": _paths("workflowPath"),
              "learn_tutor_prooflesson": _paths("packetPath")},
    "local-model": {"local_agent_run": _paths("root")},
    # WP10: the session tools join an id into the session's run or job lookup
    "relay": {**{name: {"id_args": ("run_id",)}
                 for name in ("local_agent_status", "local_agent_result")},
              # relay 0.4.0 refuses a session_id that is not a bare name; the
              # engine checks it first (GHSA-phjr-6qrc-39mw read any ledger file)
              "local_agent_sessions": {"id_args": ("session_id",)}},
}
for _action in ("status", "result", "cancel", "resume"):
    ARG_POLICY["index"][f"index.router.job.{_action}"] = {"id_args": ("job_id",)}
