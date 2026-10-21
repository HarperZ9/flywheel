"""eval_access.py -- the access statement an eval receipt carries.

A claim made through an API carries less weight than one made with weights and
training checkpoints in hand, and a reader cannot bound a claim without knowing
which it was. Every eval receipt therefore records what the evaluator could
see, over six enumerated surfaces, each granted, not_granted or unknown. It
also records which categories were redacted and who redacted them. Missing
access stays unknown: nothing here infers a grant.

check_claim_access() refuses a claim whose scope needs a surface the block does
not record as granted. Unknown counts as short, because an unrecorded grant
cannot back a claim.

Standard library only.
"""
from __future__ import annotations

SCHEMA = "flywheel.eval-access/v1"
SURFACES = ("api_outputs", "logits", "activations", "weights", "checkpoints",
            "internal_tools")
STATES = ("granted", "not_granted", "unknown")
UNKNOWN = "unknown"

# What each claim scope needs the evaluator to have seen.
CLAIM_SCOPES = {
    "output_behavior": ("api_outputs",),
    "output_distribution": ("api_outputs", "logits"),
    "internal_state": ("activations",),
    "weight_level": ("weights",),
    "training_time": ("checkpoints",),
    "deployment_tooling": ("internal_tools",),
}
DOES_NOT_PROVE = ("The access block is the evaluator's declaration, sealed with the result. "
                  "It does not show the grant was used, or that a redaction was justified.")


def _names(raw) -> str:
    if raw is None:
        return UNKNOWN
    if isinstance(raw, (list, tuple, set)):
        items = sorted({str(x).strip() for x in raw if str(x).strip()})
        return ",".join(items) if items else "none"
    return str(raw).strip() or UNKNOWN


def access_statement(declared: dict | None) -> dict:
    """{schema, surfaces{6}, redacted_categories, redacted_by}, all strings."""
    declared = dict(declared or {})
    given = dict(declared.get("surfaces") or {})
    extra = sorted(set(given) - set(SURFACES))
    if extra:
        raise ValueError(f"unknown access surfaces {extra}; expected {list(SURFACES)}")
    surfaces = {}
    for s in SURFACES:
        state = str(given.get(s, UNKNOWN))
        if state not in STATES:
            raise ValueError(f"access {s}={state!r}; expected one of {list(STATES)}")
        surfaces[s] = state
    return {"schema": SCHEMA, "surfaces": surfaces,
            "redacted_categories": _names(declared.get("redacted_categories")),
            "redacted_by": _names(declared.get("redacted_by"))}


def api_only() -> dict:
    """What a run through a provider endpoint saw: the API outputs, nothing else."""
    return access_statement({
        "surfaces": {s: ("granted" if s == "api_outputs" else "not_granted") for s in SURFACES},
        "redacted_categories": [], "redacted_by": []})


def well_formed(block) -> bool:
    try:
        return isinstance(block, dict) and access_statement(block) == block
    except (ValueError, TypeError):
        return False


def known_count(block: dict) -> int:
    return sum(v != UNKNOWN for v in block["surfaces"].values())


def check_claim_access(access: dict | None, scope: str) -> dict:
    """PASS when every surface the scope needs is granted, else UNVERIFIABLE."""
    if scope not in CLAIM_SCOPES:
        raise ValueError(f"unknown claim scope {scope!r}; expected {sorted(CLAIM_SCOPES)}")
    need = CLAIM_SCOPES[scope]
    if not isinstance(access, dict):
        return {"verdict": "UNVERIFIABLE", "code": "access_absent", "missing": list(need)}
    missing = [s for s in need if access.get("surfaces", {}).get(s) != "granted"]
    if missing:
        unknown = all(access["surfaces"].get(s) == UNKNOWN for s in missing)
        return {"verdict": "UNVERIFIABLE",
                "code": "access_unknown" if unknown else "access_not_granted",
                "missing": missing}
    return {"verdict": "PASS", "code": "access_covers_scope", "missing": []}
