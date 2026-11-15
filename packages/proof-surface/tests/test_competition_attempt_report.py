"""Competition-attempt report: the rendered packet is honest about its evidence.

The report must render the derived verdict, the source-pinned judge, the
hosted-model disclosure (or its explicit absence), the certificate-ladder rows
including a fenced layer, and the decision section.
"""

from __future__ import annotations

from proof_surface.competition_attempt import (
    build_competition_attempt_packet,
    render_report,
)

_HEX64 = "a" * 64
_HEX40 = "b" * 40

_CHALLENGE = {
    "challenge_ref": "challenge:sair-2026",
    "stage": "stage-1",
    "judge_repo": {
        "repo_ref": "github:example/judge",
        "head_sha": _HEX40,
        "observed_files": 12,
        "files_digest": _HEX64,
    },
}
_EXTRACTION = {
    "method": "boxed",
    "extracted_ref": "answers/final.txt",
    "injection_checked": True,
}
_LAYERS = [
    {
        "layer": "informal-model-output",
        "status": "EXECUTED",
        "evidence_ref": "transcript:att-1",
    },
    {
        "layer": "machine-checked-proof",
        "status": "UNAVAILABLE_FENCED",
        "probe_evidence": "probe:lean-toolchain-missing exit=127",
    },
    {
        "layer": "judge-verdict",
        "status": "EXECUTED",
        "evidence_ref": "judge:run-9",
        "passing": True,
    },
]


def _build(attempt):
    return build_competition_attempt_packet(
        sources=[{"ref": "run:comp-1", "sha256": _HEX64}],
        challenge=_CHALLENGE,
        attempt=attempt,
        answer_extraction=_EXTRACTION,
        certificate_layers=_LAYERS,
        claim="the stage-1 attempt passed the pinned judge",
        scope="one challenge, one judge revision",
        packet_id="comp-1",
    )


def test_report_renders_verdict_judge_and_ladder():
    md = render_report(
        _build(
            {
                "attempt_id": "att-1",
                "model_ref": "model:m-1",
                "external_model_calls": 3,
                "provider_receipt_ref": "receipt:prov-1",
            }
        )
    )
    assert "**Verdict: MATCH**" in md
    assert f"`{_HEX40[:12]}`" in md, "judge head_sha must be shown source-pinned"
    assert "external model calls: 3 (receipt: receipt:prov-1)" in md
    assert "| judge-verdict | EXECUTED | True | judge:run-9 |" in md
    assert (
        "| machine-checked-proof | UNAVAILABLE_FENCED | - | "
        "probe:lean-toolchain-missing exit=127 |"
    ) in md
    assert "## Decision" in md and "APPROVE" in md
    assert "—" not in md, "house voice: no em-dashes in rendered output"


def test_report_marks_undisclosed_hosted_model_usage():
    md = render_report(_build({"attempt_id": "att-1", "model_ref": "model:m-1"}))
    assert "hosted-model usage undisclosed" in md
    assert "external model calls" not in md
