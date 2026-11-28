# SPDX-License-Identifier: MIT
"""Unit and 400-trial adversarial fuzz tests for threshold_storage_attest & gpu_shader_520_gate."""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

from harness.gpu_shader_520_gate import main as gpu520_main
from harness.gpu_shader_520_gate import verify_gpu_520_files
from harness.threshold_storage_attest import main as storage_main
from harness.threshold_storage_attest import verify_threshold_storage_files
from tests._w166g_fixtures import (
    HEX64_A,
    build_gpu520_pair,
    build_hsm_receipt,
    build_raid_receipt,
    build_rlvr_and_paper8,
)


def _dump(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_threshold_storage_happy_path_disk_and_cli(tmp_path: Path) -> None:
    hp = _dump(tmp_path / "hsm.json", build_hsm_receipt(tmp_path, write_files=True))
    rp = _dump(tmp_path / "raid.json", build_raid_receipt(tmp_path, write_files=True))
    atk = {"attacks_caught": 20, "attacks_total": 20}
    v = verify_threshold_storage_files(
        hp, rp, check_binaries_on_disk=True, hsm_attacks=atk, raid_attacks=atk
    )
    assert v.passed and v.disk_binaries_verified == 10 and v.total_attacks_caught == 40
    cli = [
        "--hsm-receipt",
        str(hp),
        "--raid-receipt",
        str(rp),
        "--check-binaries-on-disk",
    ]
    assert storage_main(cli) == 0
    (tmp_path / "hsm_out/hsm.wasm").write_bytes(b"BAD!" + b"\x00" * 60)
    assert storage_main(cli) == 2


def test_gpu520_happy_path_and_cli(tmp_path: Path) -> None:
    g_man, g_rep = build_gpu520_pair()
    rlvr, p8 = build_rlvr_and_paper8()
    gm, gr = _dump(tmp_path / "gm.json", g_man), _dump(tmp_path / "gr.json", g_rep)
    rl, pp = _dump(tmp_path / "rl.json", rlvr), _dump(tmp_path / "p8.json", p8)
    v = verify_gpu_520_files(gm, gr, rl, pp)
    assert v.passed and v.certified_shaders == 520 and v.rlvr_v14_tasks == 1280
    cli = [
        "--gpu-manifest",
        str(gm),
        "--gpu-report",
        str(gr),
        "--rlvr-manifest",
        str(rl),
        "--paper8-manifest",
        str(pp),
    ]
    assert gpu520_main(cli) == 0
    bad_p8 = copy.deepcopy(p8)
    bad_p8["send_policy"] = "UPLOAD_NOW"
    _dump(pp, bad_p8)
    assert gpu520_main(cli) == 2


def _mutate_storage(h: dict[str, Any], r: dict[str, Any], atk: int) -> None:
    if atk == 0:
        h["verdict"] = "DRIFT"
    elif atk == 1:
        r["oracle"]["exit_code"] = 1
    elif atk == 2:
        h["subject"]["artifacts"].pop()
    elif atk == 3:
        r["subject"]["artifacts"][1]["rel_path"] = "../escape.exe"
    elif atk == 4:
        h["digests"]["claim_sha256"] = "sha256:bad"
    elif atk == 5:
        r["oracle"]["stdout_excerpt"] = r["oracle"]["stdout_excerpt"].replace(
            '"healed_patterns": 15', '"healed_patterns": 14'
        )
    elif atk == 6:
        h["oracle"]["stdout_excerpt"] = h["oracle"]["stdout_excerpt"].replace(
            '"t": 3', '"t": 2'
        )
    elif atk == 7:
        r["oracle"]["stdout_excerpt"] = r["oracle"]["stdout_excerpt"].replace(
            "b" * 64, HEX64_A
        )
    elif atk == 8:
        h["oracle"]["stdout_excerpt"] = h["oracle"]["stdout_excerpt"].replace(
            "25", "20"
        )
    else:
        r["subject"]["engine"] = "unknown"


def _mutate_gpu520(
    gm: dict[str, Any],
    gr: dict[str, Any],
    rl: dict[str, Any],
    p8: dict[str, Any],
    atk: int,
) -> None:
    if atk == 0:
        gm["license"] = "GPL-3.0"
    elif atk == 1:
        gm["shaders"][0]["verify_cert"] = "FAIL"
    elif atk == 2:
        gm["shaders"].pop()
    elif atk == 3:
        gr["combined_520pack_rewrites"] -= 1
    elif atk == 4:
        gr["planted_controls"]["ctrl2"]["rejected"] = False
    elif atk == 5:
        gr["validation_counts"]["spirv_val_direct"] = 7
    elif atk == 6:
        rl["push_to_hub"] = True
    elif atk == 7:
        rl["category_counts"]["planted_negative_trap"] = 32
    elif atk == 8:
        rl["counts"]["eval_tasks"] = 175
    elif atk == 9:
        p8["orcid"] = "invalid-orcid"
    elif atk == 10:
        p8["deliverables"]["page_pngs"].pop()
    else:
        p8["prior_papers_and_packs_untouched"] = False


def test_adversarial_fuzz_400_trials(tmp_path: Path) -> None:
    rng = random.Random(1662026)
    h_base, r_base = build_hsm_receipt(tmp_path), build_raid_receipt(tmp_path)
    for trial in range(200):
        h, r = copy.deepcopy(h_base), copy.deepcopy(r_base)
        _mutate_storage(h, r, rng.randrange(10))
        hp, rp = _dump(tmp_path / "hf.json", h), _dump(tmp_path / "rf.json", r)
        assert not verify_threshold_storage_files(hp, rp).passed, (
            f"storage bypass {trial}"
        )
    gm_b, gr_b = build_gpu520_pair()
    rl_b, p8_b = build_rlvr_and_paper8()
    for trial in range(200):
        gm, gr = copy.deepcopy(gm_b), copy.deepcopy(gr_b)
        rl, p8 = copy.deepcopy(rl_b), copy.deepcopy(p8_b)
        _mutate_gpu520(gm, gr, rl, p8, rng.randrange(12))
        p_gm, p_gr = _dump(tmp_path / "gmf.json", gm), _dump(tmp_path / "grf.json", gr)
        p_rl, p_p8 = _dump(tmp_path / "rlf.json", rl), _dump(tmp_path / "p8f.json", p8)
        assert not verify_gpu_520_files(p_gm, p_gr, p_rl, p_p8).passed, (
            f"gpu520 bypass {trial}"
        )
