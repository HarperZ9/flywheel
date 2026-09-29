"""The private-lane-prose gate holds, and it has teeth.

``scripts/check_private_lane_prose.py`` keeps every lane in ``HELD_LANES``
description-free on its public surfaces. These tests confirm it passes on the
real tree and that it fails when a held lane's role is not the neutral constant,
so a green run means the invariant holds rather than that the gate checks
nothing.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "priv_gate", ROOT / "scripts" / "check_private_lane_prose.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


def _neutral_dart(lane: str) -> str:
    title = lane[:1].upper() + lane[1:]
    return (f"  '{lane}': LaneIdentity(\n"
            f"    title: '{title}',\n"
            f"    identity:\n"
            f"        '{G.NEUTRAL_DART_IDENTITY}',\n"
            f"    surface: '{G.NEUTRAL_DART_SURFACE}',\n"
            f"  ),\n")


def test_the_gate_passes_on_the_real_tree():
    dart = G.DART_PATH.read_text(encoding="utf-8")
    doc = G.DOC_PATH.read_text(encoding="utf-8")
    assert G.run_checks(G.HELD_LANES, G.LANES, dart, doc) == []


def test_running_the_gate_prints_pass_and_exits_zero():
    r = subprocess.run([sys.executable, "scripts/check_private_lane_prose.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_the_gate_fails_on_a_non_neutral_role():
    """A held lane whose registry role is not neutral must be caught."""
    held = {"zzprobe": G.NEUTRAL_CARD}
    dart = _neutral_dart("zzprobe")
    bad_reg = {"zzprobe": SimpleNamespace(role="a descriptive role", organ=G.NEUTRAL_ORGAN)}
    problems = G.run_checks(held, bad_reg, dart, "")
    assert problems, "the gate accepted a non-neutral role"
    assert any("role" in p and "zzprobe" in p for p in problems), problems

    # Control: the same synthetic lane with a neutral role passes, so the failure
    # above is the role check firing and not an unrelated surface.
    ok_reg = {"zzprobe": SimpleNamespace(role=G.NEUTRAL_ROLE, organ=G.NEUTRAL_ORGAN)}
    assert G.run_checks(held, ok_reg, dart, "") == []


def _neutral_doc(lane: str) -> str:
    return (f"### {lane} 1.0.0\n\n"
            "Admitted at launch: 0 of 0 tools. T2 per granted call: 0. "
            "Not in this build: 0.\n\n"
            "| Tool | Tier | Main | Effect | Needs | Engine sets | Reason |\n"
            "|---|---|---|---|---|---|---|\n")


@pytest.mark.parametrize("surface", ["heading", "table", "admission", "comment", "duplicate"])
def test_doc_rejects_descriptions_in_structural_lines(surface):
    text = _neutral_doc("zzprobe")
    assert G.check_doc("zzprobe", text) == []
    if surface == "heading":
        text = text.replace("### zzprobe 1.0.0", "### zzprobe 1.0.0 descriptive text")
    elif surface == "table":
        text += "| descriptive text | | | | | | |\n"
    elif surface == "admission":
        text = text.replace("0 of 0 tools.", "0 of 0 tools. descriptive text")
    elif surface == "comment":
        text += "<!-- comment -->\ndescriptive text\n"
    else:
        text += "\n### zzprobe 1.0.0\ndescriptive text\n"
    assert G.check_doc("zzprobe", text), surface
