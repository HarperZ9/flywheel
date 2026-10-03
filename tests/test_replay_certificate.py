"""Replay certificate for seeded solvers.

Success criteria:
- two runs of a seeded toy solver with the same seed, weights and flags: MATCH,
  with every checkpoint digest equal and the same Merkle root;
- false-success control: flipping one weight bit inside the replayed
  computation (digests of record unchanged) gives DRIFT at the first changed
  checkpoint, and a different seed gives DRIFT, so a checker that answers MATCH
  for any two runs fails here;
- a missing determinism flag gives UNVERIFIABLE, never MATCH;
- every verdict carries the "says nothing about whether the answer is right"
  line; a cross-device DRIFT also carries the scope note;
- the module imports nothing that can run code.
"""
from __future__ import annotations

import ast
import hashlib
import random
import struct
from pathlib import Path

import pytest

from harness.certificates import replay
from harness.certificates.replay import (DRIFT, MATCH, REPLAY_DOES_NOT_PROVE,
                                         REQUIRED_FLAGS, UNVERIFIABLE, RunRecord,
                                         replay_verdict, state_digest)

FLAGS = {f: True for f in REQUIRED_FLAGS}
WEIGHTS = [0.5, -1.25, 2.0, 0.125]


def _solver(weights, seed, steps=30, flip_bit_at=None):
    """A seeded toy solver: one state vector updated by the weights and noise."""
    rng = random.Random(seed)
    state = [rng.random() for _ in weights]
    digests = []
    for step in range(steps):
        if flip_bit_at == step:
            raw = bytearray(struct.pack("<d", weights[0]))
            raw[0] ^= 1
            weights = [struct.unpack("<d", bytes(raw))[0]] + list(weights[1:])
        state = [s * 0.9 + w * 0.1 + rng.gauss(0, 0.01) for s, w in zip(state, weights)]
        digests.append(state_digest(struct.pack(f"<{len(state)}d", *state)))
    return tuple(digests)


def _record(seed=7, flags=FLAGS, device="gpu-a", driver="d1", **kw):
    wsha = hashlib.sha256(struct.pack("<4d", *WEIGHTS)).hexdigest()
    return RunRecord(weights_sha256=wsha, inputs_sha256="in", seed=seed,
                     checkpoints=_solver(WEIGHTS, seed, **kw), flags=dict(flags),
                     device=device, driver=driver)


def test_same_seed_same_flags_match():
    a, b = _record(), _record()
    out = replay_verdict(a, b)
    assert out["verdict"] == MATCH
    assert out["checkpoints"] == 30
    assert out["root_claimed"] == out["root_replayed"]


def test_control_one_flipped_weight_bit_drifts_at_that_checkpoint():
    out = replay_verdict(_record(), _record(flip_bit_at=12))
    assert out["verdict"] == DRIFT
    assert out["first_divergence"] == 12
    assert out["root_claimed"] != out["root_replayed"]


def test_control_a_different_seed_drifts():
    out = replay_verdict(_record(seed=7), _record(seed=8))
    assert out["verdict"] == DRIFT and "seed" in out["reason"]


@pytest.mark.parametrize("missing", REQUIRED_FLAGS)
def test_missing_flag_is_unverifiable_never_match(missing):
    flags = {f: f != missing for f in REQUIRED_FLAGS}
    out = replay_verdict(_record(), _record(flags=flags))
    assert out["verdict"] == UNVERIFIABLE


def test_no_checkpoints_is_unverifiable():
    empty = RunRecord(weights_sha256="w", inputs_sha256="in", seed=1, checkpoints=(),
                      flags=FLAGS)
    assert replay_verdict(empty, empty)["verdict"] == UNVERIFIABLE


def test_checkpoint_count_mismatch_drifts():
    out = replay_verdict(_record(), _record(steps=29))
    assert out["verdict"] == DRIFT and out["first_divergence"] == 29


def test_every_verdict_says_it_does_not_prove_correctness():
    for claimed, replayed in ((_record(), _record()), (_record(), _record(seed=9)),
                              (_record(), _record(flags={}))):
        assert REPLAY_DOES_NOT_PROVE in replay_verdict(claimed, replayed)["does_not_prove"]
    assert "says nothing about whether the answer is right" in REPLAY_DOES_NOT_PROVE.lower()


def test_cross_device_drift_carries_the_scope_note():
    out = replay_verdict(_record(), _record(device="gpu-b", flip_bit_at=3))
    assert out["verdict"] == DRIFT
    assert replay.CROSS_DEVICE_NOTE in out["does_not_prove"]
    same = replay_verdict(_record(), _record(flip_bit_at=3))
    assert replay.CROSS_DEVICE_NOTE not in same["does_not_prove"]


def test_module_imports_nothing_that_runs_code():
    tree = ast.parse(Path(replay.__file__).read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in ast.walk(tree)
             if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) and n.module}
    assert names <= {"__future__", "hashlib", "dataclasses", "annotations", "field",
                     "dataclass"}
