"""Tool policy data for the lanes that run agents, keep memory, publish or act:
forum, mneme, relay, local-model, writing, accountable-surface and bulletin.

Plain data, merged into ``lane_tool_policy.LANE_TOOL_POLICY``, in the same
shape as ``lane_tool_policy_evidence``. Tool names follow the payload rows'
``static_tool_names``, the engine's own ``local_mcp`` and ``writing_mcp``
tool lists, and bulletin 0.5.0's tool files (tag v0.5.0).
"""
from __future__ import annotations


def _t(effect: str, reason: str, **fields) -> dict:
    return {"effect": effect, "reason": reason, **fields}


def _main(effect: str, reason: str, **fields) -> dict:
    return _t(effect, reason, main=True, **fields)


def _health(lane: str) -> dict:
    return {f"{lane}.status": _t("read", "Identity and liveness; network-free."),
            f"{lane}.doctor": _t("read", "Readiness report; network-free.")}


_SUBMIT = ("Runs a plan through the executor. With FORUM_RUN_REAL and a granted key it "
           "spends model calls.")
_GATE = "Resolves a paused human-approval gate. An agent must not approve its own wave."
_FORUM = {
    "submit": _t("spend", _SUBMIT, tier="T2", timeout_s=120),
    "route": _t("read", "Older name for forum.route: scores a request against the roster "
                "with no model."),
    "plan": _main("model_call", "Plans a request with the configured executor without "
                  "running it: the echo executor by default, one model call with "
                  "FORUM_RUN_REAL and a granted key."),
    "status": _t("read", "Older ledger status: entry count and checkpoint."),
    "verify": _t("read", "Verifies the ledger chain."),
    "ledger_get": _t("read", "Reads one ledger entry."),
    "forum.submit": _t("spend", _SUBMIT, tier="T2", timeout_s=120),
    "forum.route": _main("read", "Scores a request against the roster with no model and "
                         "returns the decided lane."),
    "forum.prose.humanize": _t("read", "Rewrites prose by fixed rules, no model. Section "
                               "1a puts it at T2.", tier="T2"),
    "forum.prose.contract": _t("read", "Returns the deterministic communication contract."),
    **_health("forum"),
    "forum.ledger.summary": _t("read", "Summarizes the ledger."),
    "forum.ledger.capsule": _t("read", "Compacts the ledger into a capsule and returns it."),
    "forum.run.room": _t("read", "Projects the latest run into a snapshot. Section 1a "
                         "puts it at T2.", tier="T2"),
    "forum.runtime.inspect": _t("read", "Reports the executor policy without running a "
                                "model."),
    "forum.context.preflight": _t("read", "Estimates context pressure before a submit."),
    "gate_list": _t("read", "Lists paused approval gates."),
    "gate_approve": _t("approve", _GATE, tier="T2"),
    "gate_edit": _t("approve", _GATE, tier="T2"),
    "gate_reject": _t("approve", _GATE, tier="T2"),
}

_MNEME = {
    "mneme.remember": _main("state_write", "Records turns and facts in the lane's own "
                            "database. A granted key makes extraction a model call."),
    "mneme.recall": _main("read", "Retrieves memories with a ranking receipt."),
    "mneme.drift": _t("read", "Verdicts every memory against the store."),
    "mneme.to_crucible": _t("read", "Exports memories read-only and returns them. Section "
                            "1a puts it at T2.", tier="T2"),
    "mneme.replay_crucible": _t("read", "Replays a template on a read-only snapshot. "
                                "Section 1a puts it at T2.", tier="T2"),
    "mneme.provenance": _t("read", "Shows one memory's provenance receipt."),
    "mneme.origin_recheck": _t("read", "Re-reads a source file under an allowed root."),
    "mneme.forget": _t("state_write", "Deletes a memory in the lane's database and cannot "
                       "be undone; raw turn text stays (known finding 4). Section 1a puts "
                       "it at T2.", tier="T2"),
    "mneme.audit": _t("read", "Returns the forget and update history."),
    **_health("mneme"),
}

_NO_GRANTS = (("allow_write", False), ("allow_exec", False))
_RELAY_RUN = ("Runs an agent task on the model server the person set up. The engine "
              "forces write and exec off, so the run reads and proposes only.")
_RELAY_SESSION = ("A background run dies with the per-call lane child. Out of this build "
                  "until long-lived lane sessions land (WP10) and relay start is allowed "
                  "(O-3).")
_RELAY = {
    "local_agent_health": _t("network_read", "Pings the local model tiers."),
    "local_agent_chat": _t("model_call", "One completion from the first healthy tier. Not "
                           "named in section 1a.", needs=("model_server",), timeout_s=120),
    "local_agent_run": _main("model_call", _RELAY_RUN, needs=("model_server",),
                             timeout_s=300, forced_args=_NO_GRANTS),
    "local_agent_start": _t("model_call", _RELAY_SESSION, tier="T2",
                            not_in_build="per_call_child_ends_run", forced_args=_NO_GRANTS),
    "local_agent_status": _t("read", _RELAY_SESSION, not_in_build="per_call_child_ends_run"),
    "local_agent_result": _t("read", _RELAY_SESSION, not_in_build="per_call_child_ends_run"),
    "local_agent_runs": _t("read", "Lists recorded runs."),
    "local_agent_sessions": _t("read", "Lists saved sessions and re-verifies each."),
    **_health("relay"),
}

_LOCAL_RUN = ("Runs an agent task inside the picked project folder. Write and exec come "
              "from the launch and default off; the engine forces both off in the call.")
_LOCAL_MODEL = {
    "local_agent_health": _t("network_read", "Pings the local model tiers."),
    "local_agent_chat": _main("model_call", "One completion from the first healthy tier.",
                              needs=("model_server",), timeout_s=120),
    "local_agent_run": _main("model_call", _LOCAL_RUN,
                             needs=("model_server", "project_folder"), timeout_s=300,
                             forced_args=_NO_GRANTS),
    **_health("local-model"),
    "flywheel.context.health": _t("read", "Reports the Canon context bridge status. Not "
                                  "named in section 1a."),
    "flywheel.context.capture": _t("outside_write", "Writes captured context into the "
                                   "Canon context store, outside the lane folder.",
                                   tier="T2"),
    "flywheel.context.preflight": _t("read", "Searches the Canon context store. Not named "
                                     "in section 1a."),
    "receipt.verify_inclusion": _t("read", "Checks a receipt digest against the Merkle log. "
                                   "Not named in section 1a."),
}

_PREPARE = ("Prepares a proposal in the writing workspace under the Flywheel home; nothing "
            "changes until a commit. Section 1a puts the records at T2.")
_WRITING = {
    "writing.status": _t("read", "Lists the owner's writing projects."),
    "writing.doctor": _t("read", "Reports writing workflow readiness."),
    "writing.project_init": _t("state_write", _PREPARE, tier="T2"),
    "writing.section_record": _t("state_write", _PREPARE, tier="T2"),
    "writing.revision_record": _t("state_write", _PREPARE, tier="T2"),
    "writing.diagnose": _main("state_write", "Prepares a reader-flow diagnostic proposal "
                              "for a revision."),
    "writing.card_record": _t("state_write", _PREPARE, tier="T2"),
    "writing.candidate_record": _t("state_write", _PREPARE, tier="T2"),
    "writing.decision_record": _t("state_write", _PREPARE, tier="T2"),
    "writing.review_prepare": _t("state_write", _PREPARE, tier="T2"),
    "writing.export_prepare": _t("state_write", _PREPARE, tier="T2"),
    "writing.proposal_get": _t("read", "Reads one proposal preview."),
    "writing.proposal_approve": _t("approve", "Unavailable over MCP by design; approval "
                                   "runs from the CLI.", tier="T2",
                                   not_in_build="approval_cli_only"),
    "writing.proposal_commit": _t("state_write", "Commits a proposal that an approval "
                                  "outside MCP granted; changes the manuscript in the "
                                  "writing workspace. Section 1a puts the records at T2.",
                                  tier="T2"),
}

_AS = {
    "accountable-surface.perceive": _main("network_read", "Witnesses a folder, file or web "
                                          "page with its provenance digest. No gate, no "
                                          "act.", timeout_s=45),
    "accountable-surface.propose": _t("state_write", "Runs the pre-execution gate against "
                                      "the operator's grants and journals the decision; "
                                      "never acts. Section 1a puts it at T2.", tier="T2"),
    "accountable-surface.actuate": _t("actuate", "The full act loop for a wired verb.",
                                      tier="T2", needs=("actuation_grant",)),
    "accountable-surface.device_ls": _t("read", "The shipped read-only verb: lists a "
                                        "folder, with a receipt in the temp folder."),
    "accountable-surface.journal": _t("read", "Returns this session's journal."),
    "accountable-surface.receipt": _t("read", "Re-derives the receipt store."),
    **_health("accountable-surface"),
}

_BOARD_READS = ("board_rooms", "board_feed", "board_search", "board_thread", "board_post",
                "board_agents", "board_agent", "board_digest", "board_reports",
                "board_bounties", "board_bounty", "board_stats", "board_moderation_log")
_BOARD_WRITES = ("board_write_post", "board_upload_media", "board_flag_post",
                 "board_create_room", "board_create_bounty", "board_revise_bounty_terms",
                 "board_claim_bounty", "board_release_bounty_claim",
                 "board_submit_bounty_evidence", "board_review_bounty_submission",
                 "board_ack_receipt", "board_update_profile", "board_promote",
                 "board_rotate_key")
_BULLETIN = {
    "bulletin_status": _t("network_read", "The board's identity and liveness."),
    "bulletin_doctor": _t("network_read", "The board's readiness report."),
    **{name: (_main if name in ("board_rooms", "board_feed") else _t)(
        "network_read", "Reads the public board (src/tools/read.ts).", timeout_s=30)
       for name in _BOARD_READS},
    "board_inbox": _t("network_read", "Signed read of the caller's own inbox; changes "
                      "nothing.", needs=("bulletin_identity",), timeout_s=30),
    "board_whoami": _t("network_read", "Signed read about the caller's own key.",
                       needs=("bulletin_identity",), timeout_s=30),
    **{name: _t("publish", "Changes the shared board under a persistent identity "
                "(src/tools/write.ts).", tier="T2", needs=("bulletin_identity",),
                timeout_s=30)
       for name in _BOARD_WRITES},
}

AGENT_LANE_POLICY: dict[str, dict[str, dict]] = {
    "forum": _FORUM, "mneme": _MNEME, "relay": _RELAY, "local-model": _LOCAL_MODEL,
    "writing": _WRITING, "accountable-surface": _AS, "bulletin": _BULLETIN,
}
