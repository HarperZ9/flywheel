"""The T1 learn_tutor_plan cannot overwrite a session the T2 record call built.

learn writes ``tutor/<sessionId>.json`` in its working folder, the lane folder,
without checking whether the file exists. A T1 plan call naming an existing
session reset its attempts, which are the state the T2 ``learn_tutor_record``
approval exists to protect. The engine now refuses a plan call for a session
that already has a file, before learn starts, with the reason
``session_exists``. A new session id still plans at T1.
"""
from __future__ import annotations

import pytest

from harness.lane_tier_gate import argument_refusal


@pytest.fixture()
def tutor(tmp_path, monkeypatch):
    home = tmp_path / "home"
    folder = home / "lanes" / "learn" / "tutor"
    folder.mkdir(parents=True)
    (folder / "algebra-1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    return folder


def test_a_plan_for_an_existing_session_is_refused(tutor):
    refused = argument_refusal("learn", "learn_tutor_plan", {"sessionId": "algebra-1"})
    assert refused and refused["reason"] == "session_exists"
    assert refused["code"] == "LANE_TOOL_ERROR"


def test_the_existing_check_ignores_letter_case_on_windows(tutor):
    import os
    if os.name != "nt":
        pytest.skip("case-insensitive file names are a Windows fact")
    assert argument_refusal("learn", "learn_tutor_plan", {"sessionId": "ALGEBRA-1"})


def test_a_new_session_still_plans(tutor):
    assert argument_refusal("learn", "learn_tutor_plan", {"sessionId": "geometry"}) is None


def test_other_tutor_tools_read_an_existing_session(tutor):
    assert argument_refusal("learn", "learn_tutor_mastery", {"sessionId": "algebra-1"}) is None
    assert argument_refusal("learn", "learn_tutor_record", {"sessionId": "algebra-1"}) is None
