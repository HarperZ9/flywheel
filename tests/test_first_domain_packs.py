"""The first three first-party domain packs: medicine terminology,
finance claims screening, and design tokens. Each is repo data admitted
through the shipped verifier with zero code changes, which is the whole
claim of the extension mechanism. The tests also pin the integrity
chain: every oracle binding's source hash must equal the sha256 of the
fixture file it names."""
import hashlib
import json
from pathlib import Path

import pytest

from harness.domain_pack import SCHEMA, run_pack_qa, verify_pack_manifest

PACKS_ROOT = Path(__file__).resolve().parents[1] / "packs"
PACK_DIRS = ["design-tokens", "finance-compliance", "medicine-terminology"]


def _manifest(domain: str) -> dict:
    path = PACKS_ROOT / domain / "domain-pack.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _admit(domain: str) -> dict:
    return verify_pack_manifest(_manifest(domain),
                                fixtures_root=PACKS_ROOT / domain)


def test_the_three_packs_exist_and_verify_data_only():
    for domain in PACK_DIRS:
        admitted = _admit(domain)
        assert admitted["schema"] == SCHEMA
        assert admitted["state"] == "data_only"
        assert admitted["capabilities"] == ["data"]
        assert len(admitted["pack_sha256"]) == 64


def test_oracle_bindings_hash_the_fixture_files_they_name():
    for domain in PACK_DIRS:
        manifest = _manifest(domain)
        root = PACKS_ROOT / domain
        for binding in manifest["oracle_bindings"]:
            named = root / binding["source_file"]
            digest = hashlib.sha256(named.read_bytes()).hexdigest()
            assert binding["source_sha256"] == digest, (
                f"{domain}:{binding['oracle_id']} names stale evidence")


def test_every_pack_qa_detects_its_planted_false_accepts():
    for domain in PACK_DIRS:
        manifest = _manifest(domain)
        expected = {f["file"]: f["expectation"]
                    for f in manifest["fixtures"]}
        observed = []
        for name, expectation in sorted(expected.items()):
            if expectation == "correct":
                row = "accepted"
            elif expectation == "unsupported":
                row = "skipped"
            else:
                row = "refused"  # the checker catches its planted traps
            observed.append({"file": name, "observed": row})
        qa = run_pack_qa(_admit(domain), observed)
        assert qa["escaped"] == 0, f"{domain} let a false accept through"
        assert qa["detected"] == sum(
            1 for e in expected.values() if e == "incorrect")
        assert qa["resource_usage"]["within_limits"] is True
        assert qa["does_not_prove"]


def test_pack_refuses_authority_escalation():
    escalated = _manifest("medicine-terminology")
    escalated["capabilities"] = ["data", "write"]
    with pytest.raises(ValueError):
        verify_pack_manifest(escalated,
                             fixtures_root=PACKS_ROOT / "medicine-terminology")


def test_pack_refuses_a_missing_license():
    bare = _manifest("design-tokens")
    del bare["license"]
    with pytest.raises(ValueError):
        verify_pack_manifest(bare,
                             fixtures_root=PACKS_ROOT / "design-tokens")


def test_pack_refuses_a_fixture_that_left_the_pack():
    escaped = json.loads(json.dumps(_manifest("finance-compliance")))
    for fixture in escaped["fixtures"]:
        fixture["file"] = "../outside.json"
    with pytest.raises(ValueError):
        verify_pack_manifest(escaped,
                             fixtures_root=PACKS_ROOT / "finance-compliance")
