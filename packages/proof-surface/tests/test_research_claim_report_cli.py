"""Tests for the research-claim report + `telos proof research-claim` CLI."""

from __future__ import annotations

import json

from proof_surface.research_claim import (
    build_research_claim_packet,
    render_report,
    validate_research_claim_packet,
)
from proof_surface.research_claim.cli import main


def _packet(status="pass"):
    return build_research_claim_packet(
        statement="For all n >= 1, sum_{k=1}^n k = n(n+1)/2.",
        sources=[{"ref": "OEIS A000217", "url": "https://oeis.org/A000217"}],
        attempts=[{"attempt_id": "a1", "method": "numeric-probe", "result": "bounded"}],
        checks=[
            {
                "checker": "numeric-probe",
                "status": status,
                "evidence": ["n=1..1000 matched"],
            }
        ],
        claim="The identity held under the numeric probe.",
        scope="Bounded probe; not a general proof.",
        packet_id="rc-1",
        uncertainty=["bounded probe only"],
    )


def test_report_shows_statement_verdict_promotion_and_checks():
    md = render_report(_packet("pass"))
    assert "n(n+1)/2" in md
    assert "MATCH" in md
    assert "CRUCIBLE_MATCH" in md
    assert "numeric-probe" in md


def test_report_marks_unverifiable_honestly():
    md = render_report(_packet("unverifiable"))
    assert "UNVERIFIABLE" in md


_INPUT = {
    "statement": "For all n >= 1, sum_{k=1}^n k = n(n+1)/2.",
    "sources": [{"ref": "OEIS A000217", "url": "https://oeis.org/A000217"}],
    "attempts": [{"attempt_id": "a1", "method": "numeric-probe", "result": "bounded"}],
    "checks": [
        {
            "checker": "numeric-probe",
            "status": "pass",
            "evidence": ["n=1..1000 matched"],
        }
    ],
    "uncertainty": ["bounded probe only"],
}


def test_cli_emits_valid_packet_and_artifacts(tmp_path):
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(_INPUT), encoding="utf-8")
    out = tmp_path / "out"
    rc = main(
        [
            "--input",
            str(inp),
            "--claim",
            "The identity held under the numeric probe.",
            "--scope",
            "Bounded probe.",
            "--packet-id",
            "rc-1",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    packet = json.loads((out / "packet.json").read_text(encoding="utf-8"))
    assert validate_research_claim_packet(packet) == []
    assert packet["verdicts"]["overall"] == "MATCH"
    assert packet["promotion"] == "CRUCIBLE_MATCH"
    assert (out / "crucible-thesis.json").exists()
