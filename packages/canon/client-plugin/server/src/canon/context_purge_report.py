"""What a purge plan and its report say beyond the records they remove.

Every plan and report names, beside what the purge removes, the residue it
cannot remove from canon's own files and the copies canon cannot reach. Plans
and reports carry ids, roles, counts and digests, never record text or file
paths, because an MCP result enters a model context. The command line asks for
`local_detail`, which adds each event's opening words and the transcript paths
it recorded, for the owner's own terminal; those words pass through the secret
scrubber first. Every plan and report says `presence: none`: nothing checks
that the owner, rather than an agent, confirmed the plan.
"""
from __future__ import annotations

from .context_related import cited_event_ids
from .workspace.scrub import scrub

REPORT_SCHEMA = "canon.context-purge-report/v1"
PREVIEW_CHARS = 80
PRESENCE = "none"
_CLUSTERS = ("the disk clusters the old file, its rollback journal or its WAL released can "
             "still hold them until reused, because canon stores context as plaintext.")
_FREED_PLAN = "After the purge, SQLite rewrites the database file without the purged rows, but "
_FREED_DONE = "SQLite rewrote the database file without the purged rows, but "
_FREED_NOT_RUN = ("VACUUM did not run ({vacuum}), so the database file itself can still hold "
                  "the purged rows in its free pages until a confirmed purge runs again and "
                  "finishes the scrub; beyond that, ")
_LEGACY = ("Records written by canon 0.3.0 or older keep a plain sha256 of their envelope "
           "in their audit row, which can confirm a guess of the exact record.")
_OUT_OF_REACH = (
    ("client_transcripts", "The client keeps its own transcript of each session; canon "
                           "stored only its path. Delete it with the client's own tools."),
    ("earlier_query_results", "Excerpts earlier queries returned, including the context the "
                              "capture hook added to later prompts, stay in those sessions' "
                              "transcripts and with their model provider."),
    ("model_provider", "The client sent each prompt to its model provider and received each "
                       "answer from it; the provider keeps what its terms allow."),
    ("backups_and_copies", "Backups, synced folders and copies of the database file are "
                           "not changed."),
    ("returned_content_digests", "Ingest and query results carried each event's "
                                 "source_hash, an unsalted sha256 of the captured event. A "
                                 "copy a caller kept can confirm a guess of the purged "
                                 "event."),
)
DOES_NOT_PROVE = [
    "the residual scan reads the database and its journal, WAL and shared-memory files, "
    "not freed disk clusters, backups or copies elsewhere",
    "a value shorter than 16 bytes, or a run of a value shorter than min_detectable_bytes, "
    "is checked only by its row being gone",
    "a client or tool that sends the same event again stores it again",
    "no owner presence check guards the apply: any process that can reach this tool or "
    "the CLI, agents included, can apply a purge",
]


def plan_extras(view, entries: list[dict], local_detail: bool) -> dict:
    purged = {row["event_record_id"] for row in entries if row["role"] != "derived"}
    keys = {row["key"] for row in entries}
    legacy = sum(1 for row in entries if view.state.live[row["key"]].salt is None)
    events = [view.events[row["event_record_id"]] for row in entries if row["role"] != "derived"]
    extras = {
        "citing_events_kept": sum(1 for event_id, row in view.events.items()
                                  if "workspace/" + event_id not in keys
                                  and cited_event_ids(row.record) & purged),
        "residue_forecast": residue(legacy),
        "out_of_reach": out_of_reach(sum(len(_locators(row)) for row in events)),
        "presence": PRESENCE,
        "does_not_prove": list(DOES_NOT_PROVE),
    }
    if local_detail:
        extras["events"] = [_detail(view, row) for row in entries if row["role"] != "derived"]
    return extras


def residue(legacy_count: int, vacuum: str | None = None) -> list[dict]:
    """What stays in reach of the disk. A plan (`vacuum` None) speaks of the
    rewrite still to come; a report says whether VACUUM ran."""
    if vacuum is None:
        freed = _FREED_PLAN + _CLUSTERS
    elif vacuum == "done":
        freed = _FREED_DONE + _CLUSTERS
    else:
        freed = _FREED_NOT_RUN.format(vacuum=vacuum) + _CLUSTERS
    return [{"class": "freed_clusters", "note": freed},
            {"class": "legacy_fingerprints", "count": legacy_count, "note": _LEGACY}]


def _residue_after(plan: dict, scrub: dict) -> list[dict]:
    legacy = next(row["count"] for row in plan["residue_forecast"]
                  if row["class"] == "legacy_fingerprints")
    return residue(legacy, scrub["vacuum"])


def out_of_reach(transcript_count: int) -> list[dict]:
    rows = [{"class": name, "note": note} for name, note in _OUT_OF_REACH]
    rows[0]["count"] = transcript_count
    return rows


def purge_report(plan: dict, ordinals: list[int], scrub: dict, scan: dict, audit: dict) -> dict:
    """`purged` only when the chain verifies, the scan found nothing and the
    scrub finished; otherwise the first of those that failed names the status."""
    status = ("audit_failed" if not audit["ok"] else "residue_found" if scan["hits"] else
              "scrub_incomplete" if scrub["pending"] else "purged")
    report = _report_base(plan, status)
    report.update({
        "records_purged": len(ordinals),
        "tombstone_ordinals": {"first": min(ordinals), "last": max(ordinals)},
        "reason_codes": sorted({row["reason_code"] for row in plan["entries"]}),
        "audit": audit, "scrub": scrub, "scrub_pending": scrub["pending"],
        "residual_scan": {"status": "run", **scan},
        "residue": _residue_after(plan, scrub), "out_of_reach": plan["out_of_reach"],
    })
    return report


def nothing_report(plan: dict) -> dict:
    """This run removed nothing; the residue and reach earlier purges left
    are named all the same."""
    report = _report_base(plan, "nothing_to_purge")
    report.update({"records_purged": 0, "scrub_pending": False,
                   "residue": plan["residue_forecast"], "out_of_reach": plan["out_of_reach"]})
    return report


def scrub_report(plan: dict, scrub: dict) -> dict:
    """A confirmed plan that removed nothing but finished the scrub an
    interrupted purge left pending. The purged values are gone from the rows,
    so there is nothing left to scan for."""
    status = "scrub_incomplete" if scrub["pending"] else "scrub_finished"
    report = _report_base(plan, status)
    report.update({"records_purged": 0, "scrub": scrub, "scrub_pending": scrub["pending"],
                   "residual_scan": {"status": "not_run",
                                     "reason": "the purged values left the rows in an "
                                               "earlier run"},
                   "residue": _residue_after(plan, scrub), "out_of_reach": plan["out_of_reach"]})
    return report


def _report_base(plan: dict, status: str) -> dict:
    return {"schema": REPORT_SCHEMA, "status": status, "store_id": plan["store_id"],
            "workspace_id": plan["workspace_id"], "project_id": plan["project_id"],
            "plan_sha256": plan["plan_sha256"], "counts": dict(plan["counts"]),
            "already_purged": list(plan["already_purged"]),
            "citing_events_kept": plan["citing_events_kept"],
            "presence": PRESENCE, "does_not_prove": list(DOES_NOT_PROVE)}


def _detail(view, entry: dict) -> dict:
    row = view.events[entry["event_record_id"]]
    data = row.record.data
    text = scrub(str(data.get("message_text", ""))).text
    return {"event_record_id": entry["event_record_id"], "ordinal": entry["ordinal"],
            "role": entry["role"], "reason_code": entry["reason_code"],
            "message_role": data.get("message_role", "user"),
            "source_app": row.record.provenance.harness,
            "preview": text[:PREVIEW_CHARS], "preview_truncated": len(text) > PREVIEW_CHARS,
            "transcript_locators": _locators(row)}


def _locators(row) -> list[str]:
    return sorted({str(source.get("locator")) for source in row.record.data.get("sources", [])
                   if isinstance(source, dict) and source.get("source_kind") == "transcript_locator"
                   and source.get("locator")})
