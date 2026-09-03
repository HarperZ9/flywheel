"""The effort dial on the route that actually serves agent runs.

`/api/agent` is claimed by `_route_operation` before `_post` can see it, so
the effort handling that lived in the `_post` branch was unreachable: the
live path had no dial at all. These tests hold the dial on the live path,
and they fail against the operation schema that omitted `effort`.

max_steps stays the enforced budget. The dial is what the operator asked
for, and the receipt reports both, so a run whose budget diverged from its
dial says so instead of quietly reporting the nominal number.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.effort import EFFORTS
from harness.gateway_operation import _FIELDS
from harness.gateway_operation_process import _run_agent


def _operation(**over):
    base = {"goal": "g", "endpoint": "e", "max_steps": 6, "allow_write": False,
            "allow_exec": False, "stream": False,
            "data_refs": [], "credential_refs": []}
    base.update(over)
    return base


@pytest.fixture
def fake_loop(monkeypatch):
    seen: dict = {}

    def run_router_agent(goal, endpoint, **kw):
        seen.update(kw)
        return {"final": "done", "steps": 1, "tests_pass": None}

    import harness.router_agent as ra
    monkeypatch.setattr(ra, "run_router_agent", run_router_agent)
    return seen


def _run(operation, tmp_path):
    return _run_agent(operation, {}, Path(tmp_path), Path(tmp_path) / "runs")


def test_the_schema_accepts_effort_on_the_live_agent_action():
    """The falsifier for the gap: `agent.run` had no effort field, so the
    dial could not even be expressed on the route that runs agents."""
    required, optional = _FIELDS["agent.run"]
    assert "effort" in optional
    assert "effort" not in required, "a client predating the dial must still run"


def test_a_run_without_a_dial_carries_no_effort_claim(fake_loop, tmp_path):
    """An absent dial must not be reported as a default one."""
    result = _run(_operation(), tmp_path)
    assert "effort" not in result


@pytest.mark.parametrize("name", sorted(EFFORTS))
def test_every_named_dial_reaches_the_receipt(name, fake_loop, tmp_path):
    result = _run(_operation(effort=name), tmp_path)
    assert result["effort"]["name"] == name
    assert result["effort"]["max_steps"] == EFFORTS[name]["max_steps"]


def test_the_receipt_separates_the_dial_from_what_was_enforced(fake_loop,
                                                               tmp_path):
    """`high` nominates 12 steps; this operation caps at 6. The receipt must
    report the enforced budget and flag the divergence rather than assert the
    dial's nominal value as if it had been applied."""
    result = _run(_operation(effort="high", max_steps=6), tmp_path)
    effort = result["effort"]
    assert effort["name"] == "high"
    assert effort["max_steps"] == 12, "the dial's nominal value is preserved"
    assert effort["max_steps_applied"] == 6, "what actually bounded the run"
    assert effort["max_steps_overridden"] is True
    assert effort["n_candidates_applied"] is False


def test_an_agreeing_budget_is_not_flagged_as_an_override(fake_loop, tmp_path):
    result = _run(_operation(effort="low", max_steps=EFFORTS["low"]["max_steps"]),
                  tmp_path)
    assert result["effort"]["max_steps_overridden"] is False


def test_an_unknown_dial_falls_back_and_names_the_fallback(fake_loop, tmp_path):
    """Silent coercion would make two different requests indistinguishable in
    the ledger."""
    result = _run(_operation(effort="turbo"), tmp_path)
    assert result["effort"]["name"] == "standard"
    assert "turbo" in result["effort"]["note"]
