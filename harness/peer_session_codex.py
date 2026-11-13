"""Read-only observer for one Codex rollout (JSONL).

Layout, as observed on 2026-09-10 against Codex Desktop rollouts under
~/.codex/sessions/YYYY/MM/DD/rollout-<stamp>-<thread-id>.jsonl: every line
is {"timestamp", "ordinal", "type", "payload"}. The first line is a
"session_meta" record whose payload carries id, session_id, cwd, cli_version,
originator, model_provider, source, thread_source and git. Subagent
rollouts carry parent_thread_id, agent_nickname and agent_role. Later lines
are turn_context (model, cwd, effort), response_item (message, reasoning,
function_call, custom_tool_call and their outputs), event_msg (user_message,
agent_message, task_started, item_completed, token_count) and
token_usage_record. Text is never copied out.
"""
from __future__ import annotations

from collections import Counter
import re

from .peer_session_io import (DEFAULT_HEAD_BYTES, DEFAULT_TAIL_BYTES, age_seconds, iter_jsonl,
                              public_window, read_windows, text_digest)
from .peer_session_types import (HARNESS_CODEX, activity_state, base_record, bounded_counts,
                                 bucket, consistent, label)

META_STRING_KEYS = ("id", "session_id", "timestamp", "cwd", "originator", "cli_version",
                    "thread_source", "model_provider", "history_mode", "multi_agent_version",
                    "agent_nickname", "agent_role", "agent_path", "parent_thread_id")
LAST_EVENTS = ("user_message", "agent_message", "task_started", "task_complete")
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens",
              "reasoning_output_tokens", "total_tokens")
RECORD_TYPES = ("session_meta", "turn_context", "response_item", "event_msg",
                "token_usage_record", "compacted", "turn_aborted", "state")
EVENT_TYPES = ("user_message", "agent_message", "agent_reasoning", "agent_reasoning_delta",
               "agent_reasoning_section_break", "task_started", "task_complete", "token_count",
               "item_started", "item_completed", "item_updated", "error", "stream_error",
               "turn_diff", "exec_command_begin", "exec_command_end", "exec_command_output_delta",
               "patch_apply_begin", "patch_apply_end", "mcp_tool_call_begin", "mcp_tool_call_end",
               "web_search_begin", "web_search_end", "thread_settings_applied", "plan_update",
               "background_event", "notification", "shutdown_complete", "entered_review_mode",
               "exited_review_mode", "view_image_tool_call", "session_configured")
ITEM_TYPES = ("message", "reasoning", "function_call", "function_call_output", "custom_tool_call",
              "custom_tool_call_output", "local_shell_call", "web_search_call", "other")
ROLES = ("user", "assistant", "system", "developer", "tool")
COMMIT_HASH = re.compile(r"[0-9a-fA-F]{7,64}\Z")


def _str(value: object) -> str | None:
    return value if type(value) is str else None


def _git(git: object) -> dict | None:
    """Git facts without the remote URL.

    A remote URL routinely carries credentials in its userinfo (an access token
    pasted into an https remote), and it names a third party's host. Only the
    length and hash of the URL leave this observer.
    """
    if type(git) is not dict:
        return None
    commit = _str(git.get("commit_hash"))
    return {"branch": label(git.get("branch")),
            "commit_hash": commit if commit and COMMIT_HASH.match(commit) else None,
            "repository_url_ref": text_digest(git.get("repository_url"))}


def _spawn(source: object) -> dict | None:
    if type(source) is not dict or type(source.get("subagent")) is not dict:
        return None
    spawn = source["subagent"].get("thread_spawn")
    return spawn if type(spawn) is dict else None


def _session_meta(records: list[tuple[int, dict]]) -> dict | None:
    """The first session_meta in the head, plus how many the head held.

    A rollout carries one session_meta on its first line. A second one in the
    same head window is reported so a reader can see that the file does not
    have the shape the observer assumes.
    """
    seen = [rec for _offset, rec in records if rec.get("type") == "session_meta"]
    if not seen:
        return None
    payload = seen[0].get("payload")
    if type(payload) is not dict:
        return {"present": True, "payload_shape": "not_an_object",
                "session_meta_records_in_head": len(seen)}
    meta = {key: _str(payload.get(key)) for key in META_STRING_KEYS}
    source = payload.get("source")
    meta["source"] = (source if type(source) is str
                      else ("object" if type(source) is dict else None))
    spawn = _spawn(source)
    meta["spawn_depth"] = None
    if spawn is not None:
        for key in ("parent_thread_id", "agent_nickname", "agent_role", "agent_path"):
            if meta.get(key) is None:
                meta[key] = _str(spawn.get(key))
        meta["spawn_depth"] = spawn.get("depth") if type(spawn.get("depth")) is int else None
    meta["git"] = _git(payload.get("git"))
    base = payload.get("base_instructions")
    meta["base_instructions_ref"] = text_digest(base.get("text")) if type(base) is dict else None
    meta["present"] = True
    meta["session_meta_records_in_head"] = len(seen)
    return meta


def _usage(payload: dict) -> dict | None:
    info = payload.get("info")
    total = info.get("total_token_usage") if type(info) is dict else None
    if type(total) is not dict:
        return None
    return {key: total[key] for key in USAGE_KEYS if type(total.get(key)) is int}


def _event(payload: dict, ts: str | None, state: dict) -> None:
    sub = bucket(payload.get("type"), EVENT_TYPES)
    state["events"][sub] += 1
    if _str(payload.get("thread_id")):
        state["thread_ids"].append(payload["thread_id"])
    if sub in LAST_EVENTS:
        state["last"][sub] = {"timestamp": ts, "text_ref": text_digest(payload.get("message"))}
    if sub == "token_count":
        state["usage"] = _usage(payload) or state["usage"]
    if sub == "thread_settings_applied" and type(payload.get("thread_settings")) is dict:
        state["models"].append(label(payload["thread_settings"].get("model")))


def _item(payload: dict, state: dict) -> None:
    sub = bucket(payload.get("type"), ITEM_TYPES)
    state["items"][sub] += 1
    if sub == "message":
        state["roles"][bucket(payload.get("role"), ROLES)] += 1
    if sub in ("function_call", "custom_tool_call") and _str(payload.get("name")):
        state["tools"][label(payload["name"])] += 1


def _summarize(records: list[tuple[int, dict]]) -> dict:
    state = {"types": Counter(), "events": Counter(), "items": Counter(), "roles": Counter(),
             "tools": Counter(), "models": [], "cwds": [], "turn_ids": [], "thread_ids": [],
             "timestamps": [], "ordinals": [], "usage": None,
             "last": {key: None for key in LAST_EVENTS}}
    for _offset, rec in records:
        kind = bucket(rec.get("type"), RECORD_TYPES)
        state["types"][kind] += 1
        ts = _str(rec.get("timestamp"))
        if ts:
            state["timestamps"].append(ts)
        if type(rec.get("ordinal")) is int:
            state["ordinals"].append(rec["ordinal"])
        payload = rec.get("payload")
        if type(payload) is not dict:
            continue
        if kind == "turn_context":
            state["models"].append(label(payload.get("model")))
            state["cwds"].append(_str(payload.get("cwd")))
            state["turn_ids"].append(_str(payload.get("turn_id")))
        elif kind == "event_msg":
            _event(payload, ts, state)
        elif kind == "response_item":
            _item(payload, state)
        elif kind == "token_usage_record" and _str(payload.get("thread_id")):
            state["thread_ids"].append(payload["thread_id"])
    ordinals, timestamps = state["ordinals"], state["timestamps"]
    return {"record_type_counts": bounded_counts(state["types"]),
            "event_msg_counts": bounded_counts(state["events"]),
            "response_item_counts": bounded_counts(state["items"]),
            "message_role_counts": bounded_counts(state["roles"]),
            "tool_call_counts": bounded_counts(state["tools"]),
            "model": consistent(state["models"]), "cwd": consistent(state["cwds"]),
            "thread_id": consistent(state["thread_ids"]),
            "turns_seen": len({t for t in state["turn_ids"] if t}),
            "ordinal_range": [min(ordinals), max(ordinals)] if ordinals else None,
            "first_timestamp_in_window": min(timestamps) if timestamps else None,
            "last_timestamp_in_window": max(timestamps) if timestamps else None,
            "last": state["last"], "total_token_usage_reported": state["usage"]}


def observe_codex_rollout(path, *, observed_at: str, head_bytes: int = DEFAULT_HEAD_BYTES,
                          tail_bytes: int = DEFAULT_TAIL_BYTES) -> dict:
    """Describe one rollout from its head and tail windows. Never writes."""
    windows = read_windows(path, head_bytes=head_bytes, tail_bytes=tail_bytes)
    head_records, head_report = iter_jsonl(windows["head"]["_bytes"])
    if windows["source"]["tail_window_is_head_window"]:
        tail_records, tail_report = head_records, head_report
    else:
        tail_records, tail_report = iter_jsonl(windows["tail"]["_bytes"])
    meta = _session_meta(head_records) or {}
    head = _summarize(head_records)
    tail = _summarize(tail_records)
    record = base_record(HARNESS_CODEX, observed_at=observed_at)
    age = age_seconds(windows["source"]["mtime_utc"], observed_at)
    declared = consistent([meta.get("id"), meta.get("session_id")])
    thread_id = declared["value"]
    issues = []
    if not meta:
        issues.append("session_meta_absent_in_head")
    elif thread_id is None:
        issues.append("thread_id_absent_in_session_meta")
    if meta.get("session_meta_records_in_head", 0) > 1:
        issues.append("multiple_session_meta_in_head")
    if declared["basis"] == "conflict":
        issues.append("session_meta_id_conflict")
    if tail["thread_id"]["basis"] == "conflict":
        issues.append("thread_id_conflict_in_tail")
    tail_thread = tail["thread_id"]["value"]
    if thread_id and tail_thread and tail_thread != thread_id:
        issues.append("thread_id_differs_between_meta_and_tail")
    cwd = tail["cwd"]
    if cwd["value"] is None and meta.get("cwd"):
        cwd = {"value": meta["cwd"], "basis": "session_meta_only", "samples": 1}
    record.update({
        "source": windows["source"],
        "windows": {"head": {**public_window(windows["head"]), "parse": head_report},
                    "tail": {**public_window(windows["tail"]), "parse": tail_report}},
        "thread_id": thread_id, "thread_id_basis": declared,
        "thread_id_in_tail": tail["thread_id"], "session_meta": meta or None,
        "parent_thread_id": meta.get("parent_thread_id"),
        "is_subagent": bool(meta.get("parent_thread_id")),
        "model_reported": tail["model"], "cwd_reported": cwd,
        "first_timestamp_in_head": head["first_timestamp_in_window"],
        "last_timestamp_in_tail": tail["last_timestamp_in_window"],
        "tail": {k: tail[k] for k in ("record_type_counts", "event_msg_counts",
                                      "response_item_counts", "message_role_counts",
                                      "tool_call_counts", "turns_seen", "ordinal_range",
                                      "last", "total_token_usage_reported")},
        "file_age_seconds": age, "activity": activity_state(age), "issues": issues,
    })
    return record


__all__ = ["observe_codex_rollout"]
