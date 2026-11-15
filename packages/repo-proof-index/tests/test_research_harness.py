from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from score_proof_surface_research import witness_or_provenance_presence


def test_witness_or_provenance_presence_requires_positive_check() -> None:
    packet = {
        "checks": [
            {
                "tool": "local-checklist",
                "status": "warn",
                "summary": "no provenance envelope or witness receipt attached",
            }
        ]
    }

    assert not witness_or_provenance_presence(packet)


def test_witness_or_provenance_presence_accepts_passed_support_check() -> None:
    packet = {
        "checks": [
            {
                "tool": "model-provenance-validator",
                "status": "pass",
                "summary": "provenance envelope valid",
            }
        ]
    }

    assert witness_or_provenance_presence(packet)
