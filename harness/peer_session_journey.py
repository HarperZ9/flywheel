"""Project a peer-session registry into Journey v2 events.

One genesis event opens a journey for an observation run. One record_fact
event per observed session states what the bytes showed and carries the
window hashes as receipt refs. Every claim a reader could mistake for
liveness or for provider truth is stored with verdict UNVERIFIABLE and
review_required, following the norvane_capture pattern. The events are
returned to the caller; nothing is posted anywhere.
"""
from __future__ import annotations

import re
import uuid

from .evidence_json import canonical_sha256
from .journey_projection import new_genesis
from .journey_types import build_event
from .peer_session_io import text_digest
from .peer_session_types import FAILURE_SCOPE, HARNESS_CLAUDE, PUBLICATION_STATE, SCOPE

ACTOR_ID = "peer-session-observer"
LEGACY_LABEL = "peer-sessions"
UUID_SHAPE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
ULID_SHAPE = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}\Z")


def _raw_ref(session: dict) -> str | None:
    """The id string the transcript stated, whatever shape it has."""
    if session.get("harness") == HARNESS_CLAUDE:
        ident = session.get("session_id")
        value = ident.get("value") if type(ident) is dict else None
    else:
        value = session.get("thread_id")
    return value if type(value) is str else None


def _session_ref(session: dict) -> str | None:
    """The stated id, only when it is shaped like a UUID or a ULID.

    A transcript is a file that anything can write, and its id field reaches an
    event id and a fact field. Free text there would put attacker-chosen bytes
    into the journey chain, so an unshaped id is dropped and only its digest is
    reported.
    """
    value = _raw_ref(session)
    if value is None:
        return None
    return value if (UUID_SHAPE.match(value) or ULID_SHAPE.match(value)) else None


def _model_named(session: dict) -> bool:
    """Did the transcript name a model?

    A consistent() record is a dict even when the field was never emitted, so
    the value inside decides. Testing the record itself would attach a model
    claim to every session, including ones that named no model at all.
    """
    reported = session.get("model_reported")
    if type(reported) is dict:
        return reported.get("value") is not None
    return bool(session.get("models_reported"))


def _receipt_refs(session: dict) -> list[str]:
    refs = []
    for name in ("head", "tail"):
        window = session.get("windows", {}).get(name)
        if type(window) is dict and type(window.get("sha256")) is str:
            refs.append(f"sha256:{window['sha256']}")
    return sorted(set(refs)) or ["window:absent"]


def _fact(session: dict, base: str) -> dict:
    src = session.get("source", {})
    ref, raw = _session_ref(session), _raw_ref(session)
    issues = list(session.get("issues", []))
    if ref is None and raw is not None:
        issues.append("session_ref_not_id_shaped")
    return {
        "fact_id": base,
        "statement": (f"A {session['harness']} transcript of {src.get('size_bytes')} bytes "
                      f"(mtime {src.get('mtime_utc')}) was read in bounded windows at "
                      f"{session.get('observed_at')}; activity class {session.get('activity')}."),
        "receipt_refs": _receipt_refs(session), "receipt_state": "present_unchecked",
        "scope": SCOPE,
        "harness": session["harness"], "session_ref": ref,
        "session_ref_unshaped": text_digest(raw) if ref is None else None,
        "source_path": src.get("path"), "source_size_bytes": src.get("size_bytes"),
        "source_mtime_utc": src.get("mtime_utc"),
        "windows": {name: {k: w.get(k) for k in ("offset", "length", "sha256")}
                    for name, w in session.get("windows", {}).items() if type(w) is dict},
        "activity": session.get("activity"), "file_age_seconds": session.get("file_age_seconds"),
        "issues": issues,
        "content_policy": session.get("content_policy"),
    }


def _claims(session: dict, base: str, refs: list[str]) -> list[dict]:
    common = {"depends_on": [base], "verdict": "UNVERIFIABLE", "receipt_refs": refs,
              "receipt_state": "present_unchecked", "review_required": True}
    claims = [{"claim_id": f"{base}-alive", **common,
               "statement": "The session that wrote this transcript is still running.",
               "scope": "File freshness is observed; process liveness is unobserved."}]
    if _model_named(session):
        claims.append({"claim_id": f"{base}-model", **common,
                       "statement": "The model named in the transcript is the model that ran.",
                       "scope": ("A harness writes the model label it was configured "
                                 "with; the provider is unobserved here.")})
    return claims


def _failure(session: dict, base: str) -> dict:
    return {"fact_id": base,
            "statement": f"Observation of a {session.get('harness')} transcript failed: "
                         f"{session.get('error')}.",
            "receipt_refs": [f"observe-failure:{base}"], "receipt_state": "missing",
            "scope": FAILURE_SCOPE, "source_path": session.get("path")}


def registry_to_events(registry: dict, *, occurred_at: str, journey_ref: str | None = None,
                       goal: str = "Observe local Claude Code and Codex sessions") -> dict:
    """Return {"journey_ref", "events", "event_count"} for one registry. Pure; no I/O."""
    ref = journey_ref or f"jrn_{uuid.uuid4().hex}"
    intake = {"registry_sha256": registry.get("registry_sha256"),
              "discovered": registry.get("discovered"),
              "observed_count": registry.get("observed_count"),
              "observe_failures": registry.get("observe_failures"),
              "publication_state": PUBLICATION_STATE}
    events = [new_genesis(journey_ref=ref, legacy_label=LEGACY_LABEL, goal=goal, intake=intake,
                          actor_id=ACTOR_ID, occurred_at=occurred_at)]
    prior = events[0]["event_sha256"]
    for sequence, session in enumerate(registry.get("sessions", []), start=1):
        short = (_session_ref(session) or "unknown")[:12]
        base = f"peer-{sequence}-{session.get('harness', 'unknown')}-{short}"
        if session.get("observed"):
            fact = _fact(session, base)
            payload = {"facts": [fact], "claims": _claims(session, base, fact["receipt_refs"])}
        else:
            payload = {"facts": [_failure(session, base)], "claims": []}
        event = build_event(journey_ref=ref, sequence=sequence, event_type="record_fact",
                            occurred_at=occurred_at, actor_id=ACTOR_ID,
                            request_sha256=canonical_sha256(payload), payload=payload,
                            prior_event_sha256=prior)
        events.append(event)
        prior = event["event_sha256"]
    return {"journey_ref": ref, "events": events, "event_count": len(events)}


__all__ = ["ACTOR_ID", "LEGACY_LABEL", "registry_to_events"]
