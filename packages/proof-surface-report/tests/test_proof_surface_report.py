import json
import tempfile
import unittest
from pathlib import Path

from proof_surface_report import core as proof_surface_report


def write_json(directory: Path, name: str, data: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def packet(**overrides: object) -> dict:
    data = {
        "proof_surface_version": "0.1",
        "packet_id": "packet-example",
        "surface": "public-surface",
        "status": "needs-polish",
        "claims": [
            {
                "claim": "Required public files are visible.",
                "evidence": "required-file findings=0",
            }
        ],
        "checks": [
            {
                "tool": "public-surface-sweeper",
                "status": "pass",
                "summary": "required files present",
            }
        ],
        "action_items": ["Attach provenance envelope"],
    }
    data.update(overrides)
    return data


def receipt(**overrides: object) -> dict:
    data = {
        "receipt_id": "emet-verify-example",
        "verdict": "MATCH",
        "witness": {
            "implementation": "emet-python-reference",
            "spec_version": "0.2.0-draft",
            "self_sha256": "example-only",
            "check": "verify",
        },
        "subject": [
            {
                "name": "README.md",
                "digest": {"sha256": "0" * 64},
            }
        ],
        "evidence": {
            "exit_code": 0,
            "stdout_verdict_line": "MATCH README.md",
        },
        "notes": "Synthetic receipt with witness facts only.",
    }
    data.update(overrides)
    return data


class ProofSurfaceReportTests(unittest.TestCase):
    def test_valid_packet_and_receipt_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet_path = write_json(root, "packet.json", packet())
            receipt_path = write_json(root, "receipt.json", receipt())

            rendered = proof_surface_report.render_report(
                "Proof Surface Handoff Report",
                [packet_path, receipt_path],
            )

        self.assertIn("Aggregate status | needs-polish", rendered)
        self.assertIn("Witness Receipt: emet-verify-example", rendered)
        self.assertIn("Evidence: required-file findings=0", rendered)

    def test_packet_rejects_authority_language_in_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_json(
                Path(tmp),
                "packet.json",
                packet(
                    claims=[
                        {
                            "claim": "The release is certified safe to publish.",
                            "evidence": "reviewer count=1",
                        }
                    ],
                ),
            )

            with self.assertRaisesRegex(ValueError, r"\$\.claims\[0\]\.claim"):
                proof_surface_report.render_report("Proof Surface Handoff Report", [path])

    def test_packet_requires_claim_and_check_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_json(
                Path(tmp),
                "packet.json",
                packet(claims=[], checks=[]),
            )

            with self.assertRaisesRegex(ValueError, r"\$\.claims expected at least 1 item"):
                proof_surface_report.render_report("Proof Surface Handoff Report", [path])

    def test_receipt_rejects_ungoverned_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_json(Path(tmp), "receipt.json", receipt(verdict="TRUSTED"))

            with self.assertRaisesRegex(ValueError, r"\$\.verdict expected one of"):
                proof_surface_report.render_report("Proof Surface Handoff Report", [path])

    def test_receipt_rejects_authority_token_in_evidence_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_json(
                Path(tmp),
                "receipt.json",
                receipt(
                    verdict="UNVERIFIABLE",
                    evidence={
                        "exit_code": 2,
                        "stdout_verdict_line": "SAFE README.md",
                    },
                ),
            )

            with self.assertRaisesRegex(ValueError, r"\$\.evidence\.stdout_verdict_line"):
                proof_surface_report.render_report("Proof Surface Handoff Report", [path])

    def test_title_rejects_authority_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_json(Path(tmp), "packet.json", packet())

            with self.assertRaisesRegex(ValueError, r"\$\.title"):
                proof_surface_report.render_report("Certified Safe Report", [path])


if __name__ == "__main__":
    unittest.main()
