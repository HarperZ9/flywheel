# SPDX-License-Identifier: MIT
"""Unit and planted fail-closed tests for harness.buildos_attest."""

from __future__ import annotations

import ast
import copy
import hashlib
import sys
from pathlib import Path

import pytest

from harness import buildos_attest as ba

PUBLISHED_SLICE20 = {
    "img_sha256_hex": "b4cabf734830b82aa527e8e328a8bcb8d808c7407ca451c84896fe5dc451de8f",
    "boot_log_root_hex": "69016e6402ebf3883962f364b5473eb2d7b4d537e65371a79cf109dcd1a7899a",
    "sched_trace_sha_hex": "3bf89ec3554b1e2d51a5e4272ad23ab604c8999c7682daa3c07d048972d8524b",
    "vfs_inode_root_hex": "17c52355f2178ee1d9a54b099f1088b21c0fa7946300f091fa3420afd41a9456",
}


def _clean_output() -> dict:
    ref = ba.derive_triad_reference().to_dict()
    targets = {
        isa: {**ba.CLEAN_STATE, **{f: ref[f] for f in ba.ROOT_FIELDS}, "bytes": 1000 + i, "sha256": f"{i:x}" * 64}
        for i, isa in enumerate(ba.REQUIRED_ISAS, start=1)
    }
    controls = {
        atk: {isa: {"status": code, "triad_committed": 0, "fallback_slot": ba.SLOT_A, "rejected_fail_closed": True} for isa in ba.REQUIRED_ISAS}
        for atk, code in ba.ATTACKS.items()
    }
    return {"ok": True, "targets": targets, "planted_controls": controls}


def _receipt_with_files(root: Path, slice_id: int = 20, verdict: str = "MATCH") -> dict:
    stem = ba.BUILDOS_SLICES[slice_id]
    arts = []
    for isa, suffix in ba.ISA_SUFFIXES.items():
        rel = f"out/{stem}{suffix}"
        (root / "out").mkdir(parents=True, exist_ok=True)
        raw = f"{isa}-binary-{slice_id}".encode()
        (root / rel).write_bytes(raw)
        arts.append({"rel_path": rel, "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    digests = {f: "sha256:" + "a" * 64 for f in ("subject_sha256", "claim_sha256", "envelope_sha256")}
    return {
        "schema": "engine-receipt/1", "verdict": verdict, "digests": digests,
        "oracle": {"exit_code": 0, "fail_lines": 0},
        "subject": {"task_id": f"wave-slice{slice_id}-zeroc", "artifacts": arts},
    }


def test_reference_rederives_published_slice20_roots() -> None:
    assert ba.derive_triad_reference().to_dict() == PUBLISHED_SLICE20


def test_rfc6962_domain_separation_and_four_leaf_root() -> None:
    a, b = hashlib.sha256(b"a").digest(), hashlib.sha256(b"b").digest()
    assert ba.leaf_hash(a + b) != ba.node_hash(a, b)
    with pytest.raises(ValueError):
        ba.merkle_root_of_four([a, b, a])
    with pytest.raises(ValueError):
        ba.derive_sched_trace_sha([0, 1, 2])


def test_planted_epoch_rollback_changes_boot_root() -> None:
    _, rolled = ba.derive_boot_log_root(epoch=19)
    assert rolled.hex() != PUBLISHED_SLICE20["boot_log_root_hex"]


def test_triad_gate_passes_clean_five_isa_output_deterministically() -> None:
    rep = ba.verify_triad_oracle(_clean_output())
    assert rep.passed and rep.targets_committed == ba.REQUIRED_ISAS
    assert rep.attacks_rejected == rep.attacks_expected == 20 and rep.reasons == ()
    assert rep.triad_attestation_sha256 == ba.verify_triad_oracle(_clean_output()).triad_attestation_sha256
    assert rep.to_dict()["passed"] is True


@pytest.mark.parametrize("isa", ba.REQUIRED_ISAS)
def test_missing_isa_target_fails_closed(isa: str) -> None:
    out = _clean_output()
    del out["targets"][isa]
    rep = ba.verify_triad_oracle(out)
    assert not rep.passed and f"MISSING_TARGET:{isa}" in rep.reasons


@pytest.mark.parametrize("attack", list(ba.ATTACKS))
def test_attack_that_commits_triad_fails_closed(attack: str) -> None:
    out = _clean_output()
    out["planted_controls"][attack]["wasm"].update(status=1, triad_committed=1, fallback_slot=2)
    rep = ba.verify_triad_oracle(out)
    assert not rep.passed and rep.attacks_rejected == 19
    assert f"ATTACK_COMMITTED_TRIAD:{attack}:wasm" in rep.reasons
    assert f"ATTACK_NOT_SLOT_A:{attack}:wasm" in rep.reasons


@pytest.mark.parametrize("attack", list(ba.ATTACKS))
def test_missing_attack_proof_fails_closed(attack: str) -> None:
    out = _clean_output()
    del out["planted_controls"][attack]
    rep = ba.verify_triad_oracle(out)
    assert not rep.passed and f"MISSING_ATTACK:{attack}" in rep.reasons


@pytest.mark.parametrize("field", ba.ROOT_FIELDS)
def test_one_hex_root_tamper_fails_closed(field: str) -> None:
    out = _clean_output()
    val = out["targets"]["rv64-elf"][field]
    out["targets"]["rv64-elf"][field] = ("0" if val[0] != "0" else "1") + val[1:]
    rep = ba.verify_triad_oracle(out)
    assert not rep.passed and f"ROOT_MISMATCH:rv64-elf:{field}" in rep.reasons


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, 20.0, "20", None])
def test_non_integer_state_fields_fail_closed(bad: object) -> None:
    out = _clean_output()
    out["targets"]["aarch64-elf"]["epoch"] = bad
    out["planted_controls"]["boot_epoch_rollback"]["x64-pe"]["status"] = bad
    rep = ba.verify_triad_oracle(out)
    assert not rep.passed and "NON_INTEGER_FIELD:aarch64-elf:epoch" in rep.reasons
    assert any(r.startswith("ATTACK_STATUS_MISMATCH:boot_epoch_rollback:x64-pe") for r in rep.reasons)


def test_epoch_rollback_wx_and_oracle_not_ok_fail_closed() -> None:
    out = _clean_output()
    out["ok"] = False
    out["targets"]["x64-elf"]["epoch"] = 19
    out["planted_controls"]["post_boot_wx_escalation"]["x64-elf"]["rejected_fail_closed"] = False
    rep = ba.verify_triad_oracle(out)
    assert {"ORACLE_NOT_OK", "STATE_MISMATCH:x64-elf:epoch:19!=20",
            "ATTACK_NOT_FAIL_CLOSED:post_boot_wx_escalation:x64-elf"} <= set(rep.reasons)
    assert ba.verify_triad_oracle("bad").passed is False  # type: ignore[arg-type]


def test_slice_receipt_passes_with_live_disk_parity(tmp_path: Path) -> None:
    rep = ba.verify_slice_receipt(_receipt_with_files(tmp_path), 20, artifact_root=tmp_path)
    assert rep.passed and rep.isa_targets_found == ba.REQUIRED_ISAS and rep.artifacts_checked == 5


def test_slice_receipt_one_bit_binary_tamper_fails_closed(tmp_path: Path) -> None:
    rec = _receipt_with_files(tmp_path)
    target = tmp_path / "out" / "buildos_e2e_triad_zeroc.wasm"
    raw = bytearray(target.read_bytes())
    raw[0] ^= 1
    target.write_bytes(bytes(raw))
    rep = ba.verify_slice_receipt(rec, 20, artifact_root=tmp_path)
    assert not rep.passed and "ARTIFACT_HASH_MISMATCH:out/buildos_e2e_triad_zeroc.wasm" in rep.reasons


@pytest.mark.parametrize("isa", ba.REQUIRED_ISAS)
def test_slice_receipt_missing_isa_binary_fails_closed(tmp_path: Path, isa: str) -> None:
    rec = _receipt_with_files(tmp_path, slice_id=18)
    rec["subject"]["artifacts"] = [a for a in rec["subject"]["artifacts"] if not a["rel_path"].endswith(ba.ISA_SUFFIXES[isa])]
    rep = ba.verify_slice_receipt(rec, 18)
    assert not rep.passed and f"MISSING_ISA_BINARY:18:{isa}" in rep.reasons


def test_slice_receipt_envelope_and_path_escape_fail_closed(tmp_path: Path) -> None:
    rec = _receipt_with_files(tmp_path, verdict="DRIFT")
    rec["digests"]["claim_sha256"] = "sha256:XYZ"
    rec["oracle"] = {"exit_code": True, "fail_lines": 1}
    rec["subject"]["artifacts"].append({"rel_path": "../escape.bin", "sha256": "sha256:" + "b" * 64, "bytes": 3})
    rep = ba.verify_slice_receipt(rec, 20, artifact_root=tmp_path)
    assert {"VERDICT_NOT_MATCH:DRIFT", "MALFORMED_DIGEST:claim_sha256", "ORACLE_NOT_ZERO_EXIT",
            "ORACLE_FAIL_LINES_NONZERO", "ARTIFACT_PATH_ESCAPE:../escape.bin"} <= set(rep.reasons)


def test_slice_receipt_unknown_slice_wrong_task_and_missing_file(tmp_path: Path) -> None:
    assert "UNKNOWN_SLICE:21" in ba.verify_slice_receipt({}, 21).reasons
    rec = copy.deepcopy(_receipt_with_files(tmp_path, slice_id=19))
    assert "TASK_ID_SLICE_MISMATCH:wave-slice19-zeroc" in ba.verify_slice_receipt(rec, 17).reasons
    assert "MISSING_RECEIPT_FILE" in ba.verify_slice_receipt_file(tmp_path / "none.json", 17).reasons


def test_package_hygiene_loc_function_size_spdx_and_stdlib() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_files = sorted((root / "harness" / "buildos_attest").glob("*.py"))
    assert len(pkg_files) == 4
    assert set(ba.HONEST_SCOPE_LIMITS) == {"receipt_check", "triad_reference", "triad_gate"}
    for path in [*pkg_files, Path(__file__).resolve()]:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 250 and text.splitlines()[0] == "# SPDX-License-Identifier: MIT"
        assert "\u2014" not in text and "\u2013" not in text
    for path in pkg_files:
        text = path.read_text(encoding="utf-8")
        assert "HONEST_SCOPE_LIMIT" in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno - node.lineno + 1 <= 50, f"{path.name}:{node.name} > 50 LOC"
            elif isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split(".")[0] in sys.stdlib_module_names
