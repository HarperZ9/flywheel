# SPDX-License-Identifier: MIT
"""Pytest verification for packages/flywheel-bld-oracle BuildLang WASM core."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
ORACLE_BLD = PKG_DIR / "oracle.bld"
ORACLE_WASM = PKG_DIR / "oracle.wasm"
TEST_MJS = PKG_DIR / "test_oracle.mjs"
WASM_MAGIC_V1 = b"\x00asm\x01\x00\x00\x00"


def test_oracle_wasm_binary_integrity() -> None:
    assert ORACLE_BLD.is_file(), "missing oracle.bld source"
    assert ORACLE_WASM.is_file(), "missing compiled oracle.wasm binary"
    data = ORACLE_WASM.read_bytes()
    assert len(data) >= 64, f"unexpectedly small wasm binary: {len(data)} bytes"
    assert data.startswith(WASM_MAGIC_V1), (
        "oracle.wasm missing WebAssembly v1 magic header"
    )
    digest = hashlib.sha256(data).hexdigest()
    assert len(digest) == 64


def test_oracle_wasm_node_suite_and_planted_controls() -> None:
    node_bin = shutil.which("node")
    assert node_bin is not None, "node runtime required to execute test_oracle.mjs"
    res = subprocess.run(
        [node_bin, "--test", str(TEST_MJS)],
        cwd=str(PKG_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"node --test failed:\n{res.stdout}\n{res.stderr}"
