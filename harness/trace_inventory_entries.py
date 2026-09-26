"""Registry entries for FLYWHEEL_HOME and its `state/` tree (design 2.2).

Classes come from reading each writer at the code base's current revision.
`evidence` says how: observed (read in code or run) or inferred (follows from
code read but not executed). A store whose classes could not be established
has `classes=None` and a note naming what would settle it.
"""
from __future__ import annotations

from .trace_inventory import Cap, Gap, Protection, Store

META = Protection("metadata-only")
EXPORT = Gap("bulk export lands in FW-09", "FW-09")
DEL_ENC = Gap("deletion of encrypted stores lands in FW-07a", "FW-07a")
DEL_PLAIN = Gap("deletion of plaintext and legacy stores lands in FW-07b", "FW-07b")
NOT_DESIGNED = Gap("deletion of this store is not designed in this round", "7.16")


def _plain(reason: str, package: str) -> Protection:
    return Protection("plaintext-exception", reason, package)


ENC_LATER = _plain("encryption at rest lands in FW-04a", "FW-04a")
CLASSIFY_FIRST = _plain("encryption follows this classification (7.16)", "7.16")
TRACE_BOUND = Cap(
    "8 MiB per record, 32 MiB and 2048 records per trace",
    "the append is refused and the run stops with a fixed code; no shortened record is kept",
    "tests/test_gateway_agent_trace.py::test_size_limit_rejects_without_publishing_a_shortened_record")
TOOL_OUTPUT = Cap(
    "tool output cut to 4000 characters before the model and the trace see it",
    "cut with no marker (observed, local_tools.py:349,362); a kept or named copy is "
    "deferred with F-23 (7.16)", "deferred: F-23 (7.16)")
DESKTOP_WINDOW = Cap(
    "the active file keeps the newest conversations that fit: at most 60, 768 KiB "
    "and 3072 JSON nodes",
    "older conversations move to archive segments first; nothing is dropped",
    "desktop/test/chat_store_archive_test.dart::61 conversations all survive across "
    "the active file and the archive")
DESKTOP_OVERSIZE = Cap(
    "one conversation over the 1 MiB envelope or its node bound",
    "the save is refused, the latest turn stays in drafts and a metadata-only "
    "loss record is written under desktop/loss/v1",
    "desktop/test/chat_store_archive_test.dart::an oversize conversation leaves a "
    "metadata-only loss record")
DESKTOP_PHASE2 = _plain("desktop history: plaintext, kept in full, moved into "
                        "encrypted custody in phase 2", "D12")
DESKTOP_DELETE = Gap("delete from the desktop app: it removes a conversation by id "
                     "from the active file, every archive segment and the drafts; "
                     "engine-side deletion waits for phase 2 (7.9)", "7.16")

STORES = (
    Store("S1", "Gateway private agent traces", "state", ("gateway-agent-traces",),
          ("C1", "C2", "C4", "C5"), ENC_LATER, EXPORT, DEL_ENC, owner_binding="owner",
          caps=(TRACE_BOUND, TOOL_OUTPUT), invalidate=True),
    Store("S2", "Gateway operations and their results", "state", ("gateway-operations",),
          ("C1", "C4", "C5"), CLASSIFY_FIRST, EXPORT, DEL_PLAIN, owner_binding="owner",
          evidence="inferred", note="C1 only in chat.complete result files (inferred)"),
    Store("S3", "Journeys and Journey exports", "state", ("journeys", "journey-exports"),
          ("C1", "C4", "C5"), _plain("append-only event logs with their own custody model (7.10)",
                                     "7.16"), EXPORT,
          Gap("Journey events stay on deletion by design; the tombstone says so (7.10)", "7.16"),
          owner_binding="owner", note="C1 is the goal text a Journey records at intake"),
    Store("S4", "Source context snapshots", "state", ("source-context",), ("C1", "C2"),
          CLASSIFY_FIRST, EXPORT, DEL_PLAIN, owner_binding="owner", evidence="inferred"),
    Store("S5", "Continuation previews and starts", "state", ("continuation",),
          ("C1", "C4", "C5"), CLASSIFY_FIRST, EXPORT, DEL_PLAIN, owner_binding="owner"),
    Store("S5b", "Private artifacts (Journey evidence, continuation intake, Writing)",
          "state", ("artifacts",), ("C1", "C4", "C5"), CLASSIFY_FIRST, EXPORT, NOT_DESIGNED,
          owner_binding="owner", evidence="inferred"),
    Store("S6", "Native CLI profile scratch", "state", ("native-cli-profile-*",), None,
          _plain("contents unknown until experiment X5", "FW-07b"), EXPORT,
          Gap("profile directories named in a deleted trace are removed in FW-07b", "FW-07b"),
          retention="kept forever; orphans are listed (decision D18)",
          note="the Claude CLI writes these; contents unknown until experiment X5"),
    Store("S16", "Operation grants", "state", ("grants",), ("C4", "C5"), META, EXPORT,
          NOT_DESIGNED, owner_binding="owner",
          note="request and ref digests and grant state only (observed docstring)"),
    Store("S17", "Grant proposals", "state", ("grant-proposals", "gateway-grant-proposals"),
          None, CLASSIFY_FIRST, EXPORT, NOT_DESIGNED, owner_binding="owner",
          note="proposal bodies not read; may hold the operation shown for review "
               "(inferred, low)"),
    Store("S18", "Gateway subagent children", "state", ("gateway-subagents",), ("C1", "C2"),
          CLASSIFY_FIRST, EXPORT, NOT_DESIGNED, owner_binding="owner", evidence="inferred"),
    Store("S19", "Forged plans and plan runs", "state", ("plan-forge", "plan-runs"),
          ("C1", "C8"), CLASSIFY_FIRST, EXPORT, NOT_DESIGNED, owner_binding="owner",
          evidence="inferred"),
    Store("S20", "Imported Inspect evidence", "state", ("inspect-evidence",),
          ("C1", "C2", "C4"), CLASSIFY_FIRST, EXPORT, NOT_DESIGNED, owner_binding="owner",
          evidence="inferred"),
    Store("S21", "Bulletin media previews", "state", ("bulletin-media-previews",), None,
          CLASSIFY_FIRST, EXPORT, NOT_DESIGNED,
          note="media previews for Bulletin publication; contents not read"),
    Store("S22", "Gateway worker profile", "state", ("worker-profile",), None,
          CLASSIFY_FIRST, EXPORT, NOT_DESIGNED,
          note="HOME of gateway worker children (gateway_worker_env.py); whatever "
               "child tools write there is unknown"),
    Store("CL", "Custody ledger", "state", ("custody-ledger",), ("C4",), META,
          "harness.trace_custody_ledger.export_records",
          "harness.trace_custody_ledger.delete_all", owner_binding="owner",
          added_by_program=True, note="metadata only; loss records are entries of kind loss"),
    Store("S7", "Entity store (turn receipts, snapshots metadata, notes)", "home",
          ("store.db", "store.db-wal", "store.db-shm", "store.db-journal"),
          ("C1", "C4", "C5"), _plain("v2 receipts hold commitments only; legacy rows stay "
                                     "plaintext until deleted", "FW-05"), EXPORT, DEL_PLAIN,
          shape="file", owner_binding="home",
          note="receipts keep unsalted prompt and answer digests, URLs and exception text"),
    Store("S13", "Desktop chat history and drafts", "home",
          ("chats.json", "chat-drafts.json", "journey-session.json", "journey-drafts.json",
           "chats.unreadable-*.json"), ("C1", "C4", "C5"), DESKTOP_PHASE2, EXPORT,
          DESKTOP_DELETE, shape="file", owner_binding="home",
          caps=(DESKTOP_WINDOW, DESKTOP_OVERSIZE),
          note="an unreadable history file is renamed chats.unreadable-<utc>.json and "
               "never parsed or overwritten again"),
    Store("S13a", "Desktop chat archive", "home", ("chats-archive",), ("C1", "C4", "C5"),
          DESKTOP_PHASE2, EXPORT, DESKTOP_DELETE, owner_binding="home",
          retention="kept in full, no cap (decision D12)",
          note="segments <yyyymm>-<n>.json of at most 1 MiB; one copy per conversation"),
    Store("S13b", "Desktop loss records", "home", ("desktop",), ("C4",), META, EXPORT,
          NOT_DESIGNED, owner_binding="home",
          note="loss/v1 records name a conversation id, a reason code and where the "
               "original is; never text"),
    Store("S23", "Output validation ledger", "home", ("validation.jsonl",), ("C4",), META,
          EXPORT, NOT_DESIGNED, shape="file", owner_binding="home",
          note="which fields were short, never the value checked (observed)"),
)
