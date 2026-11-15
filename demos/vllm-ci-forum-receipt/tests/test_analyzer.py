from __future__ import annotations

import unittest
import json
import shutil
import tempfile
from pathlib import Path

from analyzer import analyze, duration_seconds, nearest_rank_percentile


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


class AnalyzerTests(unittest.TestCase):
    def test_duration_and_nearest_rank_are_explicit(self) -> None:
        self.assertEqual(
            duration_seconds("2026-07-21T18:37:17Z", "2026-07-21T18:41:54Z"),
            277,
        )
        self.assertEqual(nearest_rank_percentile([1, 2, 3, 4, 5], 0.9), 5)
        with self.assertRaisesRegex(ValueError, "precedes"):
            duration_seconds("2026-07-21T18:41:54Z", "2026-07-21T18:37:17Z")

    def test_precommit_snapshot_metrics_are_rederived(self) -> None:
        result = analyze(DATA)
        precommit = result["precommit"]

        self.assertEqual(precommit["sample_size"], 100)
        self.assertEqual(precommit["completed_records"], 100)
        self.assertEqual(
            precommit["conclusions"],
            {
                "action_required": 2,
                "cancelled": 35,
                "failure": 17,
                "success": 46,
            },
        )
        self.assertEqual(
            precommit["run_elapsed_seconds"],
            {
                "definition": "updated_at minus run_started_at",
                "maximum": 839,
                "median": 350.0,
                "minimum": 0,
                "p90_method": "nearest-rank",
                "p90": 591,
                "sum": 27826,
            },
        )
        self.assertIsNone(precommit["billed_runner_time_seconds"])
        self.assertIsNone(precommit["attributable_avoidable_time_seconds"])

    def test_cancelled_workflow_and_successful_job_are_not_conflated(self) -> None:
        result = analyze(DATA)
        selected = result["precommit"]["representative_runs"]["cancelled_workflow"]

        self.assertEqual(selected["run_id"], 29858770343)
        self.assertEqual(selected["workflow_conclusion"], "cancelled")
        self.assertEqual(selected["workflow_elapsed_seconds"], 434)
        self.assertEqual(selected["job_conclusion"], "success")
        self.assertEqual(selected["job_elapsed_seconds"], 263)
        self.assertEqual(selected["precommit_action_elapsed_seconds"], 245)
        self.assertIn("self-hosted", selected["runner_labels"])

    def test_macos_measurement_has_no_savings_estimate(self) -> None:
        result = analyze(DATA)
        macos = result["macos"]

        self.assertEqual(macos["sample_size"], 10)
        self.assertEqual(macos["conclusions"], {"success": 10})
        self.assertEqual(macos["run_elapsed_seconds"]["minimum"], 1340)
        self.assertEqual(macos["run_elapsed_seconds"]["maximum"], 1668)
        self.assertEqual(macos["run_elapsed_seconds"]["median"], 1499.5)
        jobs = macos["representative_run"]["jobs"]
        self.assertEqual(jobs["macos-15"]["job_elapsed_seconds"], 1326)
        self.assertEqual(jobs["macos-15"]["build_elapsed_seconds"], 297)
        self.assertEqual(jobs["macos-15"]["smoke_elapsed_seconds"], 1007)
        self.assertEqual(jobs["macos-26"]["job_elapsed_seconds"], 1329)
        self.assertEqual(jobs["macos-26"]["build_elapsed_seconds"], 299)
        self.assertEqual(jobs["macos-26"]["smoke_elapsed_seconds"], 1008)
        self.assertEqual(macos["representative_run"]["parallel_job_overlap_seconds"], 1323)
        self.assertIsNone(macos["billed_runner_time_seconds"])
        self.assertIsNone(macos["attributable_avoidable_time_seconds"])

    def test_workflow_revision_is_bound_to_representative_runs(self) -> None:
        result = analyze(DATA)
        pinned = result["provenance"]["workflows"]["precommit"]

        self.assertEqual(
            pinned["canonical_capture_ref"],
            "fca252d59efdb627549e5677263c69709590c982",
        )
        self.assertEqual(pinned["git_blob_sha"], "143fc427a49ee1736b00d2b3788f956709b67609")
        self.assertEqual(
            pinned["representative_run_refs"],
            [
                "9e7f984693d9a960ea83e5d1daa0f034d42b2513",
                "3b08ca64354bb4c4f595809b03fb63982545832e",
            ],
        )

    def test_representative_run_head_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "data"
            shutil.copytree(DATA, copied)
            path = copied / "representative-runs.json"
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            snapshot["runs"][0]["head_sha"] = "0" * 40
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "head_sha"):
                analyze(copied)

    def test_representative_run_workflow_path_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "data"
            shutil.copytree(DATA, copied)
            path = copied / "representative-runs.json"
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            snapshot["runs"][2]["path"] = ".github/workflows/other.yml"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "workflow path"):
                analyze(copied)

    def test_duplicate_representative_run_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "data"
            shutil.copytree(DATA, copied)
            path = copied / "representative-runs.json"
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            snapshot["runs"].append(dict(snapshot["runs"][0]))
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate representative run id"):
                analyze(copied)

    def test_canonical_workflow_capture_ref_mutation_is_rejected(self) -> None:
        for field in ("canonical_capture_ref", "first_capture_ref"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                copied = Path(tmp) / "data"
                shutil.copytree(DATA, copied)
                path = copied / "workflow-manifest.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                workflow = manifest["workflows"][0]
                if field == "canonical_capture_ref":
                    workflow["canonical_capture_ref"] = "0" * 40
                else:
                    workflow["captures"][0]["ref"] = "0" * 40
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "canonical capture ref"):
                    analyze(copied)

    def test_representative_run_id_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "data"
            shutil.copytree(DATA, copied)
            path = copied / "representative-runs.json"
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            snapshot["runs"][0]["id"] = 1
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "run ids"):
                analyze(copied)

    def test_representative_workflow_id_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "data"
            shutil.copytree(DATA, copied)
            path = copied / "representative-runs.json"
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            snapshot["runs"][0]["workflow_id"] = 1
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "workflow id"):
                analyze(copied)

    def test_representative_capture_ref_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "data"
            shutil.copytree(DATA, copied)
            path = copied / "workflow-manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["workflows"][0]["captures"][1]["ref"] = "0" * 40
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "head_sha"):
                analyze(copied)

    def test_workflow_byte_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "data"
            shutil.copytree(DATA, copied)
            path = copied / "pre-commit.yml"
            path.write_text(path.read_text(encoding="utf-8") + "# mutation\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Git blob|size mismatch"):
                analyze(copied)

    def test_capture_git_blob_sha_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "data"
            shutil.copytree(DATA, copied)
            path = copied / "workflow-manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["workflows"][0]["captures"][1]["git_blob_sha"] = "0" * 40
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Git blob"):
                analyze(copied)


if __name__ == "__main__":
    unittest.main()
