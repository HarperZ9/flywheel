"""Falsifiers for the absorbed intent/scope audit (ported from agent-audit).

claimed_history is the load-bearing one: it flags an agent asserting work the
witnessed ledger never did. intent_drift and scope_violations run only when a run
declares an intent or a policy.
"""
from relay.intent_audit import (
    CRITICAL,
    WARN,
    Intent,
    ScopePolicy,
    audit_intent,
    claimed_history,
    intent_drift,
    scope_violations,
)
from relay.local_session import SessionLedger


def _ledger(*entries):
    led = SessionLedger()
    for kind, content in entries:
        led.append(kind, content)
    return led


def test_claimed_history_flags_a_claim_with_no_prior_action():
    led = _ledger(("user", "add a test"),
                  ("assistant", "I previously ran the suite, so it is green."))
    findings = claimed_history(led.entries)
    assert len(findings) == 1
    assert findings[0]["detector"] == "claimed_history"
    assert findings[0]["severity"] == CRITICAL


def test_claimed_history_is_clean_when_a_tool_ran_first():
    led = _ledger(("user", "add a test"),
                  ("assistant", "run pytest"),
                  ("tool_call", 'run {"cmd": "pytest"}'),
                  ("tool_result", "ok"),
                  ("assistant", "Having run the tests, they pass."))
    assert claimed_history(led.entries) == []


def test_intent_drift_flags_a_tool_outside_the_declared_intent():
    led = _ledger(("tool_call", 'write_file {"path": "a.py"}'),
                  ("tool_call", 'run {"cmd": "curl evil"}'))
    findings = intent_drift(led.entries, Intent(tools=frozenset({"write_file", "read_file"})))
    assert [f["detail"]["tool"] for f in findings] == ["run"]
    assert findings[0]["severity"] == WARN


def test_intent_drift_is_empty_without_a_declared_intent():
    led = _ledger(("tool_call", 'run {"cmd": "x"}'))
    assert intent_drift(led.entries, None) == []


def test_scope_violation_catches_denied_tool_target_and_cap():
    led = _ledger(("tool_call", 'read_file {"path": "ok.py"}'),
                  ("tool_call", 'run {"cmd": "curl evil"}'),
                  ("tool_call", 'write_file {"path": "secret.env"}'))
    policy = ScopePolicy(denied_tools=frozenset({"run"}),
                         denied_targets=frozenset({"secret.env"}),
                         max_actions=2)
    findings = scope_violations(led.entries, policy)
    summaries = [f["summary"] for f in findings]
    assert any("run" in s for s in summaries)       # denied tool
    assert any("secret.env" in s for s in summaries)  # denied target
    assert all(f["severity"] == CRITICAL for f in findings)


def test_audit_intent_composes_detectors_and_counts():
    led = _ledger(("assistant", "I already fixed it earlier."),
                  ("tool_call", 'run {"cmd": "x"}'))
    report = audit_intent(led, intent=Intent(tools=frozenset({"read_file"})))
    assert report["schema"] == "relay.intent-audit/v1"
    kinds = {f["detector"] for f in report["findings"]}
    assert {"claimed_history", "intent_drift"} <= kinds
    assert report["critical"] >= 1  # claimed_history is critical


def test_audit_intent_accepts_a_ledger_or_bare_entries():
    led = _ledger(("assistant", "I previously did it."))
    assert audit_intent(led)["critical"] == 1
    assert audit_intent(led.entries)["critical"] == 1
