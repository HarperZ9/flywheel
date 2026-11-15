"""Terminal text for `canon context purge` and `canon context retention`.

Previews and transcript paths come from stored events, which hold whatever a
client captured, so every control and format character is printed as an
escape rather than written raw. A captured prompt cannot move the cursor, set
the window title or hide a line of the plan.
"""
from __future__ import annotations

import unicodedata

_ROLE = {"event": "", "response": " (paired)"}


def printable(text) -> str:
    out = []
    for char in str(text):
        if unicodedata.category(char) in ("Cc", "Cf", "Zl", "Zp"):
            code = ord(char)
            out.append(f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}")
        else:
            out.append(char)
    return "".join(out)


def plan_text(plan: dict) -> str:
    counts = plan["counts"]
    lines = [f"Purge plan for workspace {printable(plan['workspace_id'])}, project "
             f"{printable(plan['project_id'])}, store {plan['store_id']}",
             f"records to purge: {counts['records']} ({_count_words(counts)})"]
    for event in plan.get("events", []):
        lines.append(_event_line(event))
    lines.extend(_already_lines(plan["already_purged"]))
    if plan["scrub_pending"]:
        lines.append("scrub pending: an earlier purge was interrupted before its scrub; "
                     "applying this plan finishes it")
    lines.append(f"citing events kept: {plan['citing_events_kept']} (their query results "
                 "say the cited event was purged)")
    lines.append("residue after the purge: " + _residue_words(plan["residue_forecast"]))
    lines.append("outside canon's reach: " + _reach_words(plan["out_of_reach"]))
    for event in plan.get("events", []):
        for locator in event.get("transcript_locators", []):
            lines.append(f"  client transcript: {printable(locator)}")
    lines.append(f"plan {plan['plan_sha256']}")
    return "\n".join(lines) + "\n"


def report_text(report: dict) -> str:
    if report["status"] == "nothing_to_purge":
        return _nothing_text(report["already_purged"])
    if report["status"] in ("scrub_finished", "scrub_incomplete") and not report["records_purged"]:
        return _scrub_text(report)
    counts, scan, audit = report["counts"], report["residual_scan"], report["audit"]
    ordinals = report["tombstone_ordinals"]
    lines = [
        f"purged {report['records_purged']} records ({_count_words(counts)}); "
        f"tombstones at ordinals {ordinals['first']} to {ordinals['last']}",
        f"audit chain: {'verifies' if audit['ok'] else 'FAILS'}, {audit['length']} rows",
        f"residual scan: {scan['hits']} hits in {', '.join(scan['files'])} "
        f"({scan['windows']} windows; runs of {scan['min_detectable_bytes']} bytes or more "
        f"are found; {scan['short_values_checked_structurally']} short values checked by "
        "row absence only)",
    ]
    if scan["kept_record_matches"]:
        lines.append(f"kept records still quote the purged text {scan['kept_record_matches']} "
                     "times")
    scrub = report["scrub"]
    before = scrub.get("wal_checkpoint_before", "not_needed")
    if scrub["vacuum"] != "done" or "busy" in (before, scrub["wal_checkpoint"]):
        lines.append(f"scrub: vacuum {scrub['vacuum']}, WAL checkpoint before {before}, "
                     f"after {scrub['wal_checkpoint']}")
    lines.append("residue: " + _residue_words(report["residue"]))
    lines.append("outside canon's reach: " + _reach_words(report["out_of_reach"]))
    lines.append(f"status: {report['status']}")
    return "\n".join(lines) + "\n"


def _already_lines(already: list[str]) -> list[str]:
    if not already:
        return []
    return [f"already purged: {_events(len(already))}"] + [
        f"  {printable(event_id)}" for event_id in already]


def _nothing_text(already: list[str]) -> str:
    if not already:
        return "nothing to purge: the selection matched no captured event\n"
    verb = "was" if len(already) == 1 else "were"
    return f"nothing to purge: {len(already)} selected {_noun(len(already))} {verb} already purged\n"


def _scrub_text(report: dict) -> str:
    scrub = report["scrub"]
    return (f"nothing new to purge; finished the scrub an earlier purge left pending: "
            f"vacuum {scrub['vacuum']}, WAL checkpoint {scrub['wal_checkpoint']}\n"
            f"status: {report['status']}\n")


def _events(count: int) -> str:
    return f"{count} {_noun(count)}"


def _noun(count: int) -> str:
    return "event" if count == 1 else "events"


def _count_words(counts: dict) -> str:
    return (f"events {counts['events']}, answers {counts['responses']}, "
            f"derived {counts['derived']}")


def _event_line(event: dict) -> str:
    role = ("answer" if event["message_role"] == "assistant" else "prompt") + _ROLE[event["role"]]
    preview = printable(event["preview"]) + ("..." if event["preview_truncated"] else "")
    return (f"  ord {event['ordinal']}  {role}  {printable(event['event_record_id'])}  "
            f"{printable(event['source_app'])}  {printable(event['reason_code'])}  "
            f"\"{preview}\"")


def _residue_words(rows: list[dict]) -> str:
    words = []
    for row in rows:
        if row["class"] == "freed_clusters":
            words.append("freed disk clusters of the database, its journal and its WAL")
        elif row["class"] == "legacy_fingerprints":
            words.append(f"legacy fingerprints: {row['count']}")
    return "; ".join(words)


def _reach_words(rows: list[dict]) -> str:
    names = {"client_transcripts": "client transcripts",
             "earlier_query_results": "excerpts earlier queries returned",
             "model_provider": "the model provider", "backups_and_copies": "backups and copies",
             "returned_content_digests": "content digests earlier results returned"}
    words = []
    for row in rows:
        label = names.get(row["class"], row["class"])
        words.append(f"{label} ({row['count']})" if "count" in row else label)
    return ", ".join(words)
