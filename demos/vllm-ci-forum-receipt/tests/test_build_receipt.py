from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from forum.ledger import Ledger
from forum.storage import FileStorage

from build_receipt import _persist_forum_ledger, generate
from verify_publication import verify_publication


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReceiptBuildTests(unittest.TestCase):
    def test_read_only_publication_verifier_accepts_the_shipped_tree(self) -> None:
        result = verify_publication(ROOT)
        self.assertEqual(result["schema"], "vllm-ci-publication-verification/1")
        self.assertEqual(result["status"], "verified")

    def test_publication_verifier_ignores_git_checkout_metadata(self) -> None:
        inventory = {
            line.strip()
            for line in (ROOT / "PUBLICATION.txt").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for relative in inventory:
                destination = base / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            git_dir = base / ".git"
            git_dir.mkdir()
            (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
            self.assertEqual(verify_publication(base)["status"], "verified")

    def test_publication_inventory_and_detached_hashes_are_exact(self) -> None:
        inventory = {
            line.strip()
            for line in (ROOT / "PUBLICATION.txt").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        actual = {
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and ".ruff_cache" not in path.parts
            and ".git" not in path.parts
            and path.suffix.lower() != ".pyc"
        }
        self.assertEqual(actual, inventory)

        sums: dict[str, str] = {}
        for line in (ROOT / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
            expected_hash, relative = line.split("  ", 1)
            sums[relative] = expected_hash
        self.assertEqual(set(sums), inventory - {"SHA256SUMS.txt"})
        for relative, expected_hash in sums.items():
            self.assertEqual(digest(ROOT / relative), expected_hash, relative)

    def test_publication_docs_are_ascii_and_free_of_mojibake(self) -> None:
        for name in ("README.md", "NOTICE.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertTrue(text.isascii(), f"{name} contains non-ASCII text")
            for marker in ("â", "Ã", "�"):
                self.assertNotIn(marker, text, f"{name} contains mojibake marker {marker!r}")

    def test_manifest_binds_the_declared_upstream_license(self) -> None:
        license_path = ROOT / "UPSTREAM-LICENSE-vLLM.txt"
        notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
        self.assertTrue(license_path.is_file())
        self.assertIn(license_path.name, notice)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            generate(DATA, base / "artifacts", base / "forum-ledger")
            manifest = json.loads((base / "artifacts" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["upstream_licenses"],
                {license_path.name: digest(license_path)},
            )

    def test_shipped_generated_outputs_match_a_clean_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            generate(DATA, base / "artifacts", base / "forum-ledger")
            for directory, names in {
                "artifacts": ("analysis.json", "forum-record.json", "forum-trace.json", "manifest.json"),
                "forum-ledger": ("entries.jsonl", "payloads.jsonl"),
            }.items():
                for name in names:
                    self.assertEqual(
                        digest(ROOT / directory / name),
                        digest(base / directory / name),
                        f"stale shipped output: {directory}/{name}",
                    )

    def test_release_tree_has_no_private_path_email_or_secret_material(self) -> None:
        excluded_parts = {"__pycache__", ".ruff_cache", ".git"}
        backslash = chr(92)
        text_paths = [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and not excluded_parts.intersection(path.parts)
            and path.suffix.lower() != ".pyc"
        ]
        patterns = {
            "windows user path": r"[A-Za-z]:" + re.escape(backslash) + "Users" + re.escape(backslash),
            "unix home path": r"/(?:home|Users)/[^/\s]+",
            "UNC path": re.escape(backslash * 2) + r"[A-Za-z0-9._-]+" + re.escape(backslash),
            "email address": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
            "OpenAI-style key": r"\bsk-[A-Za-z0-9_-]{20,}\b",
            "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        }
        handle_locations: set[str] = set()
        for path in text_paths:
            text = path.read_text(encoding="utf-8")
            relative = path.relative_to(ROOT).as_posix()
            for label, pattern in patterns.items():
                self.assertIsNone(re.search(pattern, text), f"{label} found in {relative}")
            if "HarperZ9" in text:
                handle_locations.add(relative)
        self.assertEqual(
            handle_locations,
            {"NOTICE.md", "README.md", "requirements.txt", "tests/test_build_receipt.py"},
            "public Forum attribution appeared outside its declared files",
        )

    def test_forum_dependency_is_pinned_and_offline_boundary_is_documented(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(
            requirements.strip(),
            "forum @ git+https://github.com/HarperZ9/forum.git@542dda464174802aa3dc0d99e686f3edc88017cf",
        )
        self.assertIn("pip install -r requirements.txt", readme)
        self.assertIn("once Forum is installed", readme)

    def test_generation_produces_a_deep_verifying_causal_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = generate(DATA, base / "artifacts", base / "forum-ledger")
            ledger = Ledger(FileStorage(str(base / "forum-ledger")))

            self.assertTrue(ledger.verify(deep=True))
            self.assertEqual(result["forum_record"]["merkle_root"], ledger.checkpoint())
            self.assertEqual(result["forum_record"]["dangling_parents"], 0)
            self.assertEqual(
                [entry.causal_parent for entry in ledger.replay()],
                [None, 0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10],
            )
            synthesis = ledger.get_payload(ledger.get(10).payload_hash)
            self.assertEqual(synthesis["claim_state"], "verified")
            self.assertEqual(
                [binding["event_id"] for binding in synthesis["bindings"]],
                [
                    "precommit-measurement",
                    "cancelled-run-source",
                    "cancellation-hypothesis",
                    "macos-measurement",
                    "macos-job-source",
                    "cadence-hypothesis",
                    "limitations",
                ],
            )
            for binding in synthesis["bindings"]:
                entry = ledger.get(binding["seq"])
                self.assertEqual(binding["entry_hash"], entry.entry_hash)
                self.assertEqual(binding["payload_hash"], entry.payload_hash)
            last = ledger.get(11)
            payload = ledger.get_payload(last.payload_hash)
            self.assertEqual(payload["claim_state"], "inference")
            self.assertIsNone(payload["estimated_savings_seconds"])
            for entry in ledger.replay():
                self.assertIsNotNone(ledger.get_payload(entry.payload_hash))

    def test_ledger_builder_rejects_dangling_and_duplicate_event_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dangling = [
                {"actor": "a", "kind": "request", "id": "a", "payload": {}},
                {"actor": "b", "kind": "result", "id": "b", "parent": "missing", "payload": {}},
            ]
            with self.assertRaisesRegex(ValueError, "unknown or forward parent"):
                _persist_forum_ledger(dangling, base / "dangling")
            duplicate = [
                {"actor": "a", "kind": "request", "id": "same", "payload": {}},
                {"actor": "b", "kind": "result", "id": "same", "payload": {}},
            ]
            with self.assertRaisesRegex(ValueError, "duplicate event id"):
                _persist_forum_ledger(duplicate, base / "duplicate")

    def test_generation_is_deterministic_for_the_same_pinned_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a, b = Path(first), Path(second)
            ra = generate(DATA, a / "artifacts", a / "forum-ledger")
            rb = generate(DATA, b / "artifacts", b / "forum-ledger")

            self.assertEqual(ra["forum_record"]["merkle_root"], rb["forum_record"]["merkle_root"])
            for relative in (
                "analysis.json",
                "forum-trace.json",
                "forum-record.json",
                "manifest.json",
            ):
                self.assertEqual(digest(a / "artifacts" / relative), digest(b / "artifacts" / relative))
            self.assertEqual(
                digest(a / "forum-ledger" / "entries.jsonl"),
                digest(b / "forum-ledger" / "entries.jsonl"),
            )
            self.assertEqual(
                digest(a / "forum-ledger" / "payloads.jsonl"),
                digest(b / "forum-ledger" / "payloads.jsonl"),
            )

    def test_manifest_hashes_every_generated_evidence_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            generate(DATA, base / "artifacts", base / "forum-ledger")
            manifest = json.loads((base / "artifacts" / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["schema"], "vllm-ci-receipt-manifest/1")
            self.assertNotIn("manifest.json", manifest["files"])
            expected = {
                "artifacts/analysis.json",
                "artifacts/forum-record.json",
                "artifacts/forum-trace.json",
                "forum-ledger/entries.jsonl",
                "forum-ledger/payloads.jsonl",
            }
            self.assertTrue(expected.issubset(manifest["files"]))
            for relative, expected_hash in manifest["files"].items():
                self.assertEqual(digest(base / relative), expected_hash)

    def test_generated_artifacts_do_not_embed_local_paths_or_savings_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            generate(DATA, base / "artifacts", base / "forum-ledger")
            text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in list((base / "artifacts").glob("*"))
                + list((base / "forum-ledger").glob("*"))
                if path.is_file()
            )

            self.assertNotIn("C:\\", text)
            self.assertNotIn("@gmail.com", text.lower())
            self.assertNotIn('"estimated_savings_seconds": 0', text)
            self.assertIn('"estimated_savings_seconds": null', text)
            machine_values = [
                json.loads((base / "artifacts" / name).read_text(encoding="utf-8"))
                for name in ("analysis.json", "forum-trace.json", "forum-record.json")
            ]

            def assert_no_machine_savings(value: object) -> None:
                if isinstance(value, dict):
                    for key, child in value.items():
                        if "savings" in key or key in {
                            "billed_runner_time_seconds",
                            "attributable_avoidable_time_seconds",
                        }:
                            self.assertIsNone(child, f"non-null machine savings field: {key}")
                        assert_no_machine_savings(child)
                elif isinstance(value, list):
                    for child in value:
                        assert_no_machine_savings(child)

            for value in machine_values:
                assert_no_machine_savings(value)


if __name__ == "__main__":
    unittest.main()
