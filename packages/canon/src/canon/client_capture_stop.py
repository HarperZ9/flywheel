"""Stop deliveries: the client's last assistant message as a paired answer event.

Response capture is off unless the hook runs with `--capture prompts+responses`
(or `CANON_CONTEXT_CAPTURE`). Then a Stop delivery stores the client's
`last_assistant_message` as an assistant event. It is linked to the prompt
event captured for the same `prompt_id` (Claude Code) or `turn_id` (Codex) by a
`canon_event_ref` source and by `responds_to`, which is what a purge follows
when it removes a prompt together with its answer.

The answer's event id is `<native_id>-response-<segment>`. Reusing the prompt's
native id would give the answer the prompt's identity with different content,
which the store refuses as a collision. A redelivered Stop with the same text
is idempotent at its segment; a different answer for the same prompt, as when a
Stop hook asks the client to continue, takes the next segment.

An answer is stored only when the prompt it answers is in the store. The store
checks this inside the transaction that writes the answer (D-164), so a purge
of the prompt that lands while the hook runs still takes the answer with it.
A Stop whose prompt was purged, or never captured (a Claude Code prompt that arrived without a
`prompt_id` is stored under a generated id no Stop can name), stores nothing
and says which. The answer text passes through the secret scrubber first, as
a prompt does. The event records that tool calls and reasoning were not
captured. A Stop the hook does not store always returns a message saying why,
so a hook mounted on Stop never fails silently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .client_capture_payload import (
    CaptureInputError, native_prompt_id, safe_event_id, source_app_for, sources_for,
    string_field,
)
from .context_records import sha
from .workspace.scrub import scrub

CAPTURE_PROMPTS = "prompts"
CAPTURE_RESPONSES = "prompts+responses"
CAPTURE_MODES = (CAPTURE_PROMPTS, CAPTURE_RESPONSES)
MAX_SEGMENTS = 16
OFF_MESSAGE = "Canon: response capture is off; this Stop event was not stored"
NO_MESSAGE = "Canon: this Stop event carried no last assistant message and was not stored"
NO_PROMPT_ID = ("Canon: this Stop event has no prompt id to pair the answer with, "
                "so it was not stored")
NO_PROMPT = ("Canon: there is no captured prompt event for this answer to pair with, "
             "so it was not stored")
PURGED_PROMPT = ("Canon: the prompt this answer pairs with was purged, so the answer "
                 "was not stored")
STORED_AGAIN = ("Canon: this answer was purged earlier and the client sent it again; it "
                "is stored again. Purge it again to remove it.")


def capture_stop(hook: dict[str, Any], args, open_service: Callable[[], Any]) -> dict:
    """Store the answer a Stop delivery carries, or say why it was not stored."""
    if args.capture != CAPTURE_RESPONSES:
        return {"systemMessage": OFF_MESSAGE}
    message = hook.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        return {"systemMessage": NO_MESSAGE}
    source_app = source_app_for(args.client, hook)
    native_id, identified = native_prompt_id(source_app, hook)
    if not identified:
        return {"systemMessage": NO_PROMPT_ID}
    session_id = string_field(hook, "session_id")
    prompt_ref = prompt_record_id(args.workspace_id, args.project_id, source_app,
                                  session_id, native_id)
    from .context_store import ContextPairingError

    cleaned = scrub(message)
    answer = _Answer(source_app, native_id, session_id, cleaned.text, prompt_ref,
                     dict(sorted(cleaned.hits.items())))
    try:
        status = _ingest_first_free_segment(open_service(), hook, args, answer)
    except ContextPairingError as exc:
        return {"systemMessage": PURGED_PROMPT if exc.purged else NO_PROMPT}
    return {"systemMessage": STORED_AGAIN} if status == "stored_after_purge" else {}


def prompt_record_id(workspace_id: str, project_id: str, source_app: str,
                     session_id: str, native_id: str) -> str:
    """The record id the store gives the prompt event for this native id,
    computed the way context_records.make_records computes it."""
    identity = [workspace_id, project_id, source_app, session_id, safe_event_id(native_id)]
    return "context-event-" + sha(identity)


@dataclass(frozen=True)
class _Answer:
    source_app: str
    native_id: str
    session_id: str
    message: str
    prompt_ref: str
    redactions: dict


def _ingest_first_free_segment(service, hook, args, answer: _Answer) -> str:
    from .context_store import ContextCollision

    for segment in range(1, MAX_SEGMENTS + 1):
        payload = {"workspace_id": args.workspace_id, "project_id": args.project_id,
                   "event": _answer_event(hook, args, answer, segment)}
        try:
            return service.ingest(payload)["status"]
        except ContextCollision:
            continue
    raise CaptureInputError(f"this prompt already has {MAX_SEGMENTS} different stored "
                            "answers; the answer was not stored")


def _answer_event(hook, args, answer: _Answer, segment: int) -> dict[str, Any]:
    ref = {"source_id": "prompt_event", "source_kind": "canon_event_ref",
           "ref": answer.prompt_ref, "extraction_status": "completed"}
    transcript = hook.get("transcript_path") if args.transcript_locator == "path" else None
    locators = [source for source in sources_for(answer.source_app, answer.native_id,
                                                 transcript if isinstance(transcript, str)
                                                 else None)
                if source["source_kind"] == "transcript_locator"]
    coverage = {
        "response": "captured",
        "tool_calls": "not_captured",
        "reasoning": "not_captured",
        "transcript": "locator_only_not_read" if locators else "locator_not_recorded",
        "pairing": "prompt_event_found",
    }
    if answer.redactions:
        coverage["redactions"] = answer.redactions
    return {
        "event_id": f"{safe_event_id(answer.native_id)}-response-{segment}",
        "source_app": answer.source_app,
        "native_id": answer.native_id,
        "session_id": answer.session_id,
        "message_text": answer.message,
        "message_role": "assistant",
        "responds_to": answer.prompt_ref,
        "container_id": args.container_id,
        "coverage": coverage,
        "sources": [ref] + locators,
    }
