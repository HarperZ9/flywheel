# SPDX-License-Identifier: MIT
"""Unit and 400-trial adversarial fuzz tests for mir_assurance_gate and rsi_pareto_gate."""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

from harness.mir_assurance_gate import main as mir_main
from harness.mir_assurance_gate import verify_mir_assurance_files
from harness.rsi_pareto_gate import main as rsi_main
from harness.rsi_pareto_gate import verify_rsi_pareto_files
from tests._mir_rsi_fixtures import (
    build_mir_payloads,
    build_rsi_payload,
    build_wasm_pack,
    write_mir_files,
)


def test_mir_assurance_happy_path_and_cli(tmp_path: Path) -> None:
    eff, wcet, ct, det = write_mir_files(tmp_path, build_mir_payloads())
    v = verify_mir_assurance_files(eff, wcet, ct, det)
    assert v.passed and v.pillars_verified == 4 and v.total_violations == 0
    cli_ok = [
        "--effect",
        str(eff),
        "--wcet",
        str(wcet),
        "--ct",
        str(ct),
        "--det",
        str(det),
    ]
    assert mir_main(cli_ok) == 0
    bad = build_mir_payloads()
    bad["wcet"]["buildos_core_sweep"]["modules"][0]["has_recursion"] = True
    b = write_mir_files(tmp_path, bad)
    cli_bad = [
        "--effect",
        str(b[0]),
        "--wcet",
        str(b[1]),
        "--ct",
        str(b[2]),
        "--det",
        str(b[3]),
    ]
    assert mir_main(cli_bad) == 2


def test_rsi_pareto_happy_path_disk_check_and_cli(tmp_path: Path) -> None:
    rsi_p, pack_p = tmp_path / "rsi.json", tmp_path / "pack.json"
    rsi_p.write_text(json.dumps(build_rsi_payload()), encoding="utf-8")
    pack_p.write_text(
        json.dumps(build_wasm_pack(tmp_path, write_wasm=True)), encoding="utf-8"
    )
    v = verify_rsi_pareto_files(rsi_p, pack_p, check_wasm_on_disk=True)
    assert v.passed and v.wasm_disk_checked == 100 and v.goodhart_rollback_pct == 100.0
    cli = [
        "--rsi-report",
        str(rsi_p),
        "--wasm-manifest",
        str(pack_p),
        "--check-wasm-on-disk",
    ]
    assert rsi_main(cli) == 0
    (tmp_path / "modules/demo_000.wasm").write_bytes(b"NOTWASM" + b"\x00" * 65)
    assert rsi_main(cli) == 2


def _mutate_mir(p: dict[str, dict[str, Any]], atk: int) -> None:
    sw = {k: p[k]["buildos_core_sweep"] for k in p}
    if atk == 0:
        sw["effect"]["modules"][0]["module_effects"] = ["net"]
    elif atk == 1:
        sw["effect"]["zero_egress_all"] = False
    elif atk == 2:
        sw["effect"]["denied_effects"] = ["fs", "net"]
    elif atk == 3:
        sw["wcet"]["recursion_free_all"] = False
    elif atk == 4:
        sw["wcet"]["max_single_frame_bytes"] = 2056
    elif atk == 5:
        sw["wcet"]["modules"][1]["max_stack_bytes"] = 4128
    elif atk == 6:
        sw["ct"]["total_violations"] = 1
    elif atk == 7:
        p["ct"]["planted_side_channel_controls_caught"] = 2
    elif atk == 8:
        sw["det"]["modules"][2]["bit_exact_deterministic"] = False
    elif atk == 9:
        sw["det"]["modules"][0]["file"] = "rogue.bl"
    elif atk == 10:
        p["det"]["commit_sha"] = "bad-sha"
    else:
        sw["ct"]["modules"][0]["constant_time_verified"] = False


def _mutate_rsi_wasm(r: dict[str, Any], w: dict[str, Any], atk: int) -> None:
    if atk == 0:
        r["metrics"]["goodhart_traps_blocked"] = 39.0
    elif atk == 1:
        r["metrics"]["regressions"] = 1.0
    elif atk == 2:
        r["parity"]["max_3way_err"] = 1e-9
    elif atk == 3:
        r["metrics"]["final_score"] = r["metrics"]["initial_score"]
    elif atk == 4:
        r["controls"]["ctrl3_forged_superopt_cert_rejected"] = False
    elif atk == 5:
        r["metrics"]["compound_gain_x"] = float("nan")
    elif atk == 6:
        w["modules"][7]["license"] = "GPL-3.0"
    elif atk == 7:
        w["modules"][3]["wasm_path"] = "../escape.wasm"
    elif atk == 8:
        w["total_bytes"] = 1_400_000
    elif atk == 9:
        w["modules"][5]["slug"] = w["modules"][4]["slug"]
    elif atk == 10:
        w["modules"].pop()
    else:
        r["verdict"] = "FAIL"


def test_adversarial_fuzz_400_trials(tmp_path: Path) -> None:
    rng = random.Random(1602026)
    mir_base = build_mir_payloads()
    for trial in range(200):
        mut = copy.deepcopy(mir_base)
        _mutate_mir(mut, rng.randrange(12))
        eff, wcet, ct, det = write_mir_files(tmp_path, mut)
        assert not verify_mir_assurance_files(eff, wcet, ct, det).passed, (
            f"MIR bypass {trial}"
        )
    rsi_base = build_rsi_payload()
    pack_base = build_wasm_pack(tmp_path, write_wasm=False)
    for trial in range(200):
        r, w = copy.deepcopy(rsi_base), copy.deepcopy(pack_base)
        _mutate_rsi_wasm(r, w, rng.randrange(12))
        rp, wp = tmp_path / "r_fuzz.json", tmp_path / "w_fuzz.json"
        rp.write_text(json.dumps(r), encoding="utf-8")
        wp.write_text(json.dumps(w), encoding="utf-8")
        assert not verify_rsi_pareto_files(rp, wp).passed, f"RSI bypass {trial}"
