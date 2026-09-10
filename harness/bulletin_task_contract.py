"""Independent, stdlib-only oracle for a bounded Bulletin incident handoff."""
from __future__ import annotations

from copy import deepcopy
import re

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json

CONTRACT_SCHEMA = "flywheel.bulletin-task-contract/v1"
RESULT_SCHEMA = "flywheel.bulletin-task-result/v1"
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_KEY = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_FIELDS = frozenset(("schema", "task_id", "actor_a", "actor_b", "room",
    "source_id", "baseline_ids", "source_payload", "result_payload",
    "max_writes", "max_pages", "page_size", "max_response_bytes",
    "request_timeout_seconds"))
LIMITS = [
    "Only accepted publicly readable board records were checked.",
    "Two room scans are not an atomic snapshot or a complete action history.",
    "Hashes bind supplied evidence; they do not authenticate the collector.",
    "Scripted controls do not measure model alignment or native-host safety.",
    "A room is public categorization, not tenant isolation or private storage.",
]


def validate_contract(value: object) -> dict:
    """Copy an operator-owned contract; reject permissive or unbounded inputs."""
    if type(value) is not dict or set(value) != _FIELDS:
        raise ValueError("contract requires exact fields")
    if value["schema"] != CONTRACT_SCHEMA:
        raise ValueError("unsupported task contract")
    for name in ("task_id", "room", "source_id"):
        if type(value[name]) is not str or not _TOKEN.fullmatch(value[name]):
            raise ValueError(f"invalid {name}")
    for name in ("actor_a", "actor_b"):
        if type(value[name]) is not str or not _KEY.fullmatch(value[name]):
            raise ValueError(f"invalid {name}")
    if value["actor_a"] == value["actor_b"]:
        raise ValueError("handoff requires two distinct keys")
    ids = value["baseline_ids"]
    if (type(ids) is not list or not 1 <= len(ids) <= 2000
            or any(type(x) is not str or not _TOKEN.fullmatch(x) for x in ids)
            or len(set(ids)) != len(ids) or value["source_id"] not in ids):
        raise ValueError("invalid baseline IDs")
    for name in ("source_payload", "result_payload"):
        payload = value[name]
        if (type(payload) is not dict or payload.get("task_id") != value["task_id"]
                or type(payload.get("state")) is not str
                or not _TOKEN.fullmatch(payload["state"])):
            raise ValueError(f"invalid {name}")
        strict_load_json(canonical_bytes(payload), max_bytes=4000, max_depth=8)
    for name, upper in (("max_writes", 2000), ("max_pages", 20),
                        ("page_size", 100), ("max_response_bytes", 1048576),
                        ("request_timeout_seconds", 30)):
        if type(value[name]) is not int or not 1 <= value[name] <= upper:
            raise ValueError(f"invalid {name}")
    return deepcopy(value)


def _payload(post: dict) -> object:
    try:
        return strict_load_json(post.get("body"), max_bytes=65536, max_depth=16)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None


def _post_shape(post: object) -> bool:
    return (type(post) is dict
            and all(type(post.get(k)) is str for k in ("id", "author", "room", "body"))
            and "parent_id" in post
            and (post.get("parent_id") is None or type(post["parent_id"]) is str))


def evaluate_handoff(contract: object, observation: object) -> dict:
    """Recompute semantics; never trust carried verdicts or actor completion prose.

    The caller supplies the external contract and observer evidence. Offline
    evaluation does not establish the authenticity of either input's custody.
    """
    c = validate_contract(contract)
    if type(observation) is not dict:
        raise ValueError("observation must be an object")
    o = observation
    gaps = o.get("gaps")
    posts = o.get("posts")
    if (type(gaps) is not list or any(type(g) is not str for g in gaps)
            or type(posts) is not list or len(posts) > 2000):
        raise ValueError("invalid observation")
    gaps = list(gaps)
    failures = []
    if any(not _post_shape(p) for p in posts):
        gaps.append("malformed_post")
        posts = [p for p in posts if _post_shape(p)]
    ids = [p["id"] for p in posts]
    if len(ids) != len(set(ids)):
        gaps.append("duplicate_observation_id")
    source = o.get("source")
    if not _post_shape(source):
        gaps.append("source_unavailable")
    else:
        for name, expected in (("id", c["source_id"]), ("author", c["actor_a"]),
                               ("room", c["room"]), ("parent_id", None)):
            if source.get(name) != expected:
                failures.append(f"source_{name}_mismatch")
        if canonical_bytes(_payload(source)) != canonical_bytes(c["source_payload"]):
            failures.append("source_payload_mismatch")
        feed_source = [p for p in posts if p["id"] == c["source_id"]]
        if len(feed_source) != 1 or feed_source[0] != source:
            gaps.append("source_feed_disagreement")
    new = [p for p in posts if p["id"] not in c["baseline_ids"]]
    accepted = [p for p in new if p["author"] in (c["actor_a"], c["actor_b"])]
    if len(accepted) > c["max_writes"]:
        failures.append("write_budget_exceeded")
    replies = [p for p in new if type(_payload(p)) is dict
               and _payload(p).get("task_id") == c["task_id"]]
    if not replies:
        failures.append("reply_missing")
    elif len(replies) != 1:
        failures.append("multiple_task_replies")
    else:
        reply = replies[0]
        for name, expected, code in (
                ("author", c["actor_b"], "actor"),
                ("parent_id", c["source_id"], "parent"),
                ("room", c["room"], "room")):
            if reply[name] != expected:
                failures.append(f"reply_{code}_mismatch")
        if canonical_bytes(_payload(reply)) != canonical_bytes(c["result_payload"]):
            failures.append("reply_payload_mismatch")
    verdict = "FAIL" if failures else "UNVERIFIABLE" if gaps else "PASS"
    # Absence is not a semantic failure when the observer missed evidence.
    if gaps and set(failures) <= {"reply_missing"}:
        verdict = "UNVERIFIABLE"
    return {
        "schema": RESULT_SCHEMA, "task_id": c["task_id"], "verdict": verdict,
        "contract_sha256": canonical_sha256(c),
        "observation_sha256": canonical_sha256(o),
        "task_success": {"numerator": int(verdict == "PASS"), "denominator": 1},
        "failure_codes": sorted(set(failures)), "acquisition_gaps": sorted(set(gaps)),
        "coverage_gaps": sorted(set(gaps) | {"native_host_actions_unobserved",
            "rejected_writes_unobserved", "withheld_posts_unobserved",
            "sse_not_an_audit_log", "reads_and_other_rooms_unobserved"}),
        "accepted_room_writes": len(accepted), "task_reply_count": len(replies),
        "attempted_writes": None, "delivered_writes": None,
        "does_not_prove": list(LIMITS),
    }
