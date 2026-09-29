"""Policy reasons read as plain reasons, with no internal decision ids.

Product-truth review of the 1.1.0 change, PT-8. The approval sheet prints a
tool's policy reason on its "Why:" line, and 70 of 233 reasons carried ids
from a decision file that is not in the repository ("Section 1a", O-8, WP10,
O-14, C-5) or called the person approving the call "the operator".
"""
from __future__ import annotations

import re
from pathlib import Path

from harness.lane_tool_policy import LANE_TOOL_POLICY

ROOT = Path(__file__).resolve().parents[1]

INTERNAL = re.compile(
    r"\b(?:O-\d+|C-\d+|WP\d+|FW-\d+|Section \d+[a-z]?|POLICY-DECISION)\b|\boperator\b",
    re.IGNORECASE)


def test_the_pattern_catches_the_forms_it_is_for():
    """Control: each form the review counted is caught."""
    for text in ("Section 1a puts it at T2.", "Held out of this build (O-8).",
                 "on the relay lane session (WP10)", "at T2 (C-5).",
                 "the operator's grants", "Not named in section 1a."):
        assert INTERNAL.search(text), text
    assert not INTERNAL.search("Runs the gate against your grants and journals the decision.")


def test_no_policy_reason_carries_an_internal_id():
    found = [f"{lane}.{name}: {entry.reason}"
             for lane, tools in LANE_TOOL_POLICY.items()
             for name, entry in tools.items() if INTERNAL.search(entry.reason)]
    assert found == []


def test_the_public_policy_page_carries_the_rendered_tables_in_plain_words():
    """docs/features/lane-tool-policy.md is the page the release notes point
    readers to; the policy review record stays in its own register."""
    from scripts.render_lane_policy_review import render_tables
    page = (ROOT / "docs" / "features" / "lane-tool-policy.md").read_text(encoding="utf-8")
    assert render_tables() in page
    prose = re.sub(r"`[^`]*`", "", page)          # tool names such as telos.operator.doctor
    assert not INTERNAL.search(prose)
