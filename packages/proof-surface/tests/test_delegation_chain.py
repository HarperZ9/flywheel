"""Tests for the delegation chain (Contract / Layer 1): identity & scoped authority.

Exercises:
  * structural validation -- additionalProperties:false, required fields, closed
    enums, hex binding format, ISO timestamps, recursive forbidden-field guard,
    and the structural rule that the ROOT hop's 'from' party is a human,
  * the hash-chain binding (compute_binding determinism + tamper-evidence),
  * verify_delegation's closed verdict lattice: VALID / DENIED / UNVERIFIABLE,
    including monotonic scope attenuation (anti-escalation), integrity, expiry,
    revocation, effective-scope intersection, the action/target check, and the
    honest signature-assurance path.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from proof_surface.delegation_chain import (
    DELEGATION_VERSION,
    DENIED,
    FORBIDDEN_FIELDS,
    UNVERIFIABLE,
    VALID,
    compute_binding,
    compute_chain_binding,
    validate_delegation_chain,
    verify_delegation,
)

CONF = Path(__file__).resolve().parents[1] / "conformance" / "delegation-chain" / "v0.1"

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)  # between 2024 grants and 2999 expiries

HUMAN = {"id": "alice@example.com", "kind": "human", "key_id": "key-alice-1"}
AGENT_A = {"id": "agent:planner", "kind": "agent", "key_id": "key-a"}
AGENT_B = {"id": "agent:executor", "kind": "agent", "key_id": "key-b"}


def _hop(
    frm,
    to,
    actions,
    targets,
    *,
    granted="2024-01-01T00:00:00Z",
    expires="2999-01-01T00:00:00Z",
    revoked=False,
):
    return {
        "from": copy.deepcopy(frm),
        "to": copy.deepcopy(to),
        "scope": {"allowed_actions": list(actions), "allowed_targets": list(targets)},
        "granted_at": granted,
        "expires_at": expires,
        "revoked": revoked,
    }


def _sign(hops):
    """Attach real hash-chain bindings in order."""
    out, prev = [], ""
    for h in hops:
        h = copy.deepcopy(h)
        h.pop("binding", None)
        h["binding"] = compute_binding(h, prev)
        prev = h["binding"]
        out.append(h)
    return out


def _chain(*hops, chain_id="c1", chain_binding=None):
    hops = list(hops)
    if chain_binding is None:
        leaf = hops[-1]["binding"] if hops else ""
        chain_binding = compute_chain_binding(chain_id, len(hops), leaf)
    return {
        "delegation_version": DELEGATION_VERSION,
        "chain_id": chain_id,
        "hops": hops,
        "chain_binding": chain_binding,
    }


# --- structural validation: happy path -------------------------------------


def test_minimal_valid_chain_passes():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], ["repo:x"])]))
    assert validate_delegation_chain(chain) == []


def test_valid_fixtures_from_disk_pass():
    for name in ("single-hop.chain.json", "two-hop-attenuating.chain.json"):
        data = json.loads((CONF / "valid" / name).read_text(encoding="utf-8"))
        assert validate_delegation_chain(data) == [], name


def test_non_object_rejected():
    assert validate_delegation_chain(["not", "an", "object"])


# --- forbidden-field guard --------------------------------------------------


def test_forbidden_field_rejected_at_root():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    chain["prefire"] = {"x": 1}
    assert any("forbidden" in i.message for i in validate_delegation_chain(chain))


def test_every_prefire_key_forbidden_at_root():
    for key in FORBIDDEN_FIELDS:
        chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
        chain[key] = "x"
        issues = validate_delegation_chain(chain)
        assert any(i.path == f"$.{key}" and "forbidden" in i.message for i in issues), (
            key
        )


def test_forbidden_field_rejected_nested_in_party():
    hop = _hop(HUMAN, AGENT_A, ["read"], [])
    hop["from"]["sovereignty_capsule"] = {"y": 2}
    issues = validate_delegation_chain(_chain(*_sign([hop])))
    assert any(
        "sovereignty_capsule" in i.path and "forbidden" in i.message for i in issues
    )


# --- additionalProperties:false & enums -------------------------------------


def test_unknown_root_field_rejected():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    chain["approved_by"] = "auto"
    assert any(i.path == "$.approved_by" for i in validate_delegation_chain(chain))


def test_unknown_hop_field_rejected():
    hop = _hop(HUMAN, AGENT_A, ["read"], [])
    signed = _sign([hop])
    signed[0]["weight"] = 1  # added after signing -- unknown field
    assert any("weight" in i.path for i in validate_delegation_chain(_chain(*signed)))


def test_delegation_version_const():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    chain["delegation_version"] = "2.0"
    assert any(
        i.path == "$.delegation_version" for i in validate_delegation_chain(chain)
    )


def test_party_kind_closed_enum():
    hop = _hop(HUMAN, {"id": "x", "kind": "robot"}, ["read"], [])
    assert any(
        i.path.endswith(".to.kind")
        for i in validate_delegation_chain(_chain(*_sign([hop])))
    )


# --- structural rule: authority originates with a human ---------------------


def test_root_from_must_be_human():
    hop = _hop(AGENT_A, AGENT_B, ["read"], [])  # root 'from' is an agent
    issues = validate_delegation_chain(_chain(*_sign([hop])))
    assert any(i.path == "$.hops[0].from.kind" for i in issues)


def test_non_root_from_may_be_agent():
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["read"], []),
                _hop(AGENT_A, AGENT_B, ["read"], []),  # agent delegating onward is fine
            ]
        )
    )
    assert validate_delegation_chain(chain) == []


# --- binding format & required fields ---------------------------------------


def test_bad_binding_format_rejected():
    hop = _hop(HUMAN, AGENT_A, ["read"], [])
    hop["binding"] = "deadbeef"
    assert any(
        i.path.endswith(".binding") for i in validate_delegation_chain(_chain(hop))
    )


def test_empty_hops_rejected():
    assert any(i.path == "$.hops" for i in validate_delegation_chain(_chain()))


def test_non_iso_expiry_rejected():
    hop = _hop(HUMAN, AGENT_A, ["read"], [], expires="soon")
    assert any(
        i.path.endswith(".expires_at")
        for i in validate_delegation_chain(_chain(*_sign([hop])))
    )


def test_expiry_must_be_after_grant():
    hop = _hop(
        HUMAN,
        AGENT_A,
        ["read"],
        [],
        granted="2030-01-01T00:00:00Z",
        expires="2029-01-01T00:00:00Z",
    )
    assert any(
        i.path.endswith(".expires_at")
        for i in validate_delegation_chain(_chain(*_sign([hop])))
    )


# --- compute_binding ---------------------------------------------------------


def test_compute_binding_is_deterministic():
    hop = _hop(HUMAN, AGENT_A, ["read"], ["repo:x"])
    assert compute_binding(hop, "") == compute_binding(copy.deepcopy(hop), "")


def test_compute_binding_changes_with_content():
    h1 = _hop(HUMAN, AGENT_A, ["read"], [])
    h2 = _hop(HUMAN, AGENT_A, ["read", "write"], [])  # wider scope
    assert compute_binding(h1, "") != compute_binding(h2, "")


def test_compute_binding_chains_on_previous():
    hop = _hop(AGENT_A, AGENT_B, ["read"], [])
    assert compute_binding(hop, "aa" * 32) != compute_binding(hop, "bb" * 32)


# --- verify_delegation: VALID happy paths -----------------------------------


def test_verify_single_hop_valid():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read", "write"], ["repo:x"])]))
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == VALID


def test_verify_two_hop_attenuating_valid():
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["read", "summarize", "write"], []),
                _hop(AGENT_A, AGENT_B, ["read", "summarize"], ["repo:proof-surface"]),
            ]
        )
    )
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == VALID
    assert v.effective_scope["allowed_actions"] == ["read", "summarize"]
    assert v.effective_scope["allowed_targets"] == ["repo:proof-surface"]
    assert v.effective_scope["any_target"] is False


def test_verify_valid_fixture_from_disk():
    data = json.loads(
        (CONF / "valid" / "two-hop-attenuating.chain.json").read_text(encoding="utf-8")
    )
    assert verify_delegation(data, now=NOW).verdict == VALID


# --- verify_delegation: DENIED on escalation (the core anti-escalation rule) -


def test_verify_denies_action_escalation():
    # hop1 claims 'write' which hop0 (the human grant) does not hold.
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["read"], []),
                _hop(AGENT_A, AGENT_B, ["read", "write"], []),
            ]
        )
    )
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == DENIED
    assert any("escalates" in r for r in v.reasons)


def test_verify_denies_target_widening_to_any():
    # parent restricted to a target; child claims ANY target (empty list).
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["read"], ["repo:x"]),
                _hop(AGENT_A, AGENT_B, ["read"], []),
            ]
        )
    )
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == DENIED
    assert any("widen" in r or "ANY target" in r for r in v.reasons)


def test_verify_denies_target_escalation_outside_parent():
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["read"], ["repo:x"]),
                _hop(AGENT_A, AGENT_B, ["read"], ["repo:y"]),  # y not within {x}
            ]
        )
    )
    assert verify_delegation(chain, now=NOW).verdict == DENIED


def test_verify_allows_target_narrowing():
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["read"], ["repo:x", "repo:y"]),
                _hop(AGENT_A, AGENT_B, ["read"], ["repo:x"]),  # subset -- fine
            ]
        )
    )
    assert verify_delegation(chain, now=NOW).verdict == VALID


# --- verify_delegation: DENIED on broken integrity --------------------------


def test_verify_denies_tampered_scope():
    signed = _sign([_hop(HUMAN, AGENT_A, ["read"], [])])
    signed[0]["scope"]["allowed_actions"].append("write")  # tamper after signing
    v = verify_delegation(_chain(*signed), now=NOW)
    assert v.verdict == DENIED
    assert any("integrity" in r for r in v.reasons)


def test_verify_denies_tampered_downstream_hop():
    signed = _sign(
        [
            _hop(HUMAN, AGENT_A, ["read", "write"], []),
            _hop(AGENT_A, AGENT_B, ["read"], []),
        ]
    )
    signed[1]["to"]["id"] = "agent:impostor"  # tamper hop1 after signing
    assert verify_delegation(_chain(*signed), now=NOW).verdict == DENIED


# --- verify_delegation: DENIED on expiry / not-yet-effective / revocation ----


def test_verify_denies_expired_hop():
    chain = _chain(
        *_sign([_hop(HUMAN, AGENT_A, ["read"], [], expires="2024-06-01T00:00:00Z")])
    )
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == DENIED
    assert any("expired" in r for r in v.reasons)


def test_verify_denies_not_yet_effective():
    chain = _chain(
        *_sign(
            [
                _hop(
                    HUMAN,
                    AGENT_A,
                    ["read"],
                    [],
                    granted="2999-01-01T00:00:00Z",
                    expires="3000-01-01T00:00:00Z",
                )
            ]
        )
    )
    assert verify_delegation(chain, now=NOW).verdict == DENIED


def test_verify_denies_revoked_hop():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [], revoked=True)]))
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == DENIED
    assert any("revoked" in r for r in v.reasons)


def test_effective_expiry_is_earliest():
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["read"], [], expires="2030-01-01T00:00:00Z"),
                _hop(AGENT_A, AGENT_B, ["read"], [], expires="2027-01-01T00:00:00Z"),
            ]
        )
    )
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == VALID
    assert v.effective_expiry == "2027-01-01T00:00:00Z"


# --- verify_delegation: effective-scope intersection over 3 hops ------------


def test_effective_scope_intersection_three_hops():
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["a", "b", "c"], []),
                _hop(AGENT_A, AGENT_B, ["a", "b"], ["t1", "t2"]),
                _hop(AGENT_B, AGENT_A, ["a"], ["t1"]),
            ]
        )
    )
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == VALID
    assert v.effective_scope["allowed_actions"] == ["a"]
    assert v.effective_scope["allowed_targets"] == ["t1"]


# --- verify_delegation: action / target authorisation against effective scope


def test_verify_action_in_scope_allows():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read", "write"], ["repo:x"])]))
    assert (
        verify_delegation(chain, action="read", target="repo:x", now=NOW).verdict
        == VALID
    )


def test_verify_action_out_of_scope_denies():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], ["repo:x"])]))
    v = verify_delegation(chain, action="write", target="repo:x", now=NOW)
    assert v.verdict == DENIED
    assert any("not within the leaf's effective authority" in r for r in v.reasons)


def test_verify_target_out_of_scope_denies():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], ["repo:x"])]))
    assert (
        verify_delegation(chain, action="read", target="repo:y", now=NOW).verdict
        == DENIED
    )


def test_verify_restricted_target_requires_target_arg():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], ["repo:x"])]))
    # action given but no target, while scope restricts targets -> default-deny
    assert verify_delegation(chain, action="read", now=NOW).verdict == DENIED


def test_verify_any_target_allows_missing_target_arg():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))  # any target
    assert verify_delegation(chain, action="read", now=NOW).verdict == VALID


# --- verify_delegation: structural failure collapses to DENIED --------------


def test_verify_structurally_invalid_is_denied():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    chain["prefire"] = {"x": 1}
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == DENIED
    assert any("structurally invalid" in r for r in v.reasons)


# --- verify_delegation: honest signature-assurance path ---------------------


def test_require_signatures_without_verifier_is_unverifiable():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    v = verify_delegation(chain, now=NOW, require_signatures=True)
    assert v.verdict == UNVERIFIABLE
    assert any("will not fabricate" in r for r in v.reasons)


def test_require_signatures_with_passing_verifier_is_valid():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    v = verify_delegation(
        chain, now=NOW, require_signatures=True, signature_verifier=lambda hop: True
    )
    assert v.verdict == VALID


def test_require_signatures_with_failing_verifier_is_denied():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    v = verify_delegation(
        chain, now=NOW, require_signatures=True, signature_verifier=lambda hop: False
    )
    assert v.verdict == DENIED


def test_require_signatures_with_raising_verifier_is_denied():
    # A SUPPLIED verifier that raises did not confirm the signature -- the check was
    # attempted and failed, which is a positive failure (DENIED), not "the tool
    # cannot check" (UNVERIFIABLE is reserved for the no-verifier case).
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))

    def boom(hop):
        raise RuntimeError("verifier offline")

    v = verify_delegation(
        chain, now=NOW, require_signatures=True, signature_verifier=boom
    )
    assert v.verdict == DENIED


# --- target supplied without action (authorization bypass guard) ------------


def test_verify_target_without_action_is_denied():
    # A target with no action skipped the whole scope check and returned VALID.
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], ["repo:x"])]))
    v = verify_delegation(chain, target="repo:x", now=NOW)
    assert v.verdict == DENIED
    assert any("without an action" in r for r in v.reasons)


def test_verify_target_without_action_denied_even_for_any_target():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))  # any target
    assert verify_delegation(chain, target="anything", now=NOW).verdict == DENIED


# --- DENIED / UNVERIFIABLE verdicts must carry the deny-safe empty scope ------


def _assert_deny_safe(scope):
    assert scope == {"allowed_actions": [], "allowed_targets": [], "any_target": False}


def test_revoked_denied_has_deny_safe_scope():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], ["repo:x"], revoked=True)]))
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == DENIED
    _assert_deny_safe(v.effective_scope)
    assert v.effective_expiry is None


def test_expired_denied_has_deny_safe_scope():
    chain = _chain(
        *_sign(
            [_hop(HUMAN, AGENT_A, ["read"], ["repo:x"], expires="2024-06-01T00:00:00Z")]
        )
    )
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == DENIED
    _assert_deny_safe(v.effective_scope)


def test_escalation_denied_has_deny_safe_scope():
    chain = _chain(
        *_sign(
            [
                _hop(HUMAN, AGENT_A, ["read"], []),
                _hop(AGENT_A, AGENT_B, ["read", "write"], []),
            ]
        )
    )
    v = verify_delegation(chain, now=NOW)
    assert v.verdict == DENIED
    _assert_deny_safe(v.effective_scope)


def test_unverifiable_has_deny_safe_scope():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    v = verify_delegation(chain, now=NOW, require_signatures=True)
    assert v.verdict == UNVERIFIABLE
    _assert_deny_safe(v.effective_scope)
    assert v.effective_expiry is None


# --- whole-chain commitment: truncation & extension --------------------------


def test_verify_denies_chain_truncation():
    # Build a valid 2-hop chain, then strip the attenuating leaf hop while keeping
    # the original (n=2) chain_binding. Each remaining hop still re-derives, but the
    # whole-chain commitment no longer matches.
    signed = _sign(
        [
            _hop(HUMAN, AGENT_A, ["read", "write", "delete"], []),
            _hop(AGENT_A, AGENT_B, ["read"], []),
        ]
    )
    full = _chain(*signed)
    truncated = {**full, "hops": [signed[0]]}  # keeps full["chain_binding"]
    v = verify_delegation(truncated, now=NOW)
    assert v.verdict == DENIED
    assert any("truncated or extended" in r for r in v.reasons)


def test_verify_denies_chain_extension():
    # Valid 1-hop chain; attacker appends a forged-but-attenuating hop with a
    # correctly-derived per-hop binding, but does not update chain_binding.
    signed = _sign([_hop(HUMAN, AGENT_A, ["read"], [])])
    full = _chain(*signed)  # chain_binding commits n=1
    attacker = {"id": "agent:impostor", "kind": "agent"}
    forged = _hop(AGENT_A, attacker, ["read"], [])
    forged["binding"] = compute_binding(forged, signed[0]["binding"])
    extended = {**full, "hops": [signed[0], forged]}  # still n=1 chain_binding
    v = verify_delegation(extended, now=NOW)
    assert v.verdict == DENIED
    assert any("truncated or extended" in r for r in v.reasons)


# --- external anchor: pinned chain_binding -----------------------------------


def test_pinned_chain_binding_match_is_valid():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    v = verify_delegation(chain, now=NOW, pinned_chain_binding=chain["chain_binding"])
    assert v.verdict == VALID


def test_pinned_chain_binding_mismatch_is_denied():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    v = verify_delegation(chain, now=NOW, pinned_chain_binding="f" * 64)
    assert v.verdict == DENIED
    assert any("pinned" in r for r in v.reasons)


# --- additional structural validation ----------------------------------------


def test_chain_binding_required():
    chain = _chain(*_sign([_hop(HUMAN, AGENT_A, ["read"], [])]))
    del chain["chain_binding"]
    assert any(i.path == "$.chain_binding" for i in validate_delegation_chain(chain))


def test_duplicate_scope_entries_rejected():
    hop = _hop(HUMAN, AGENT_A, ["read", "read"], [])
    issues = validate_delegation_chain(_chain(*_sign([hop])))
    assert any("duplicate" in i.message for i in issues)


def test_whitespace_only_string_rejected():
    hop = _hop(HUMAN, AGENT_A, ["read"], [])
    chain = _chain(*_sign([hop]))
    chain["chain_id"] = "   "  # whitespace-only, .strip() empties it
    assert any(i.path == "$.chain_id" for i in validate_delegation_chain(chain))


def test_forbidden_field_rejected_nested_in_scope():
    hop = _hop(HUMAN, AGENT_A, ["read"], [])
    hop["scope"]["prefire"] = {"x": 1}
    issues = validate_delegation_chain(_chain(*_sign([hop])))
    assert any("prefire" in i.path and "forbidden" in i.message for i in issues)


# --- conformance manifest ----------------------------------------------------


def test_conformance_fixtures_match_manifest():
    manifest = json.loads((CONF / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        data = json.loads((CONF / fixture["path"]).read_text(encoding="utf-8"))
        issues = validate_delegation_chain(data)
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid: {issues}"
        else:
            assert issues, f"{fixture['path']} should be invalid but got no issues"


# --- schema / Python validator parity (dev-only; runtime stays stdlib-only) ---


def test_json_schema_matches_python_validator():
    """Every conformance fixture must get the SAME verdict from the published JSON
    Schema and from the reference Python validator. This guards against the schema
    and the validator drifting apart (e.g. the root-must-be-human rule, ISO
    timestamp patterns, non-whitespace patterns, the forbidden-field guard)."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "delegation-chain.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    manifest = json.loads((CONF / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        data = json.loads((CONF / fixture["path"]).read_text(encoding="utf-8"))
        schema_ok = validator.is_valid(data)
        python_ok = validate_delegation_chain(data) == []
        assert schema_ok == python_ok, (
            f"{fixture['path']}: schema={schema_ok} python={python_ok} -- "
            f"schema and validator disagree"
        )
