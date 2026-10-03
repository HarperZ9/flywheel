"""replay.py -- the replay certificate: did the same seeded computation run twice?

A claimant records a run: digests of the weights, the inputs and the seed, the
determinism flags it ran under, the device and driver, and a digest of the
decoded state at each fixed checkpoint. A replayer runs the same thing on the
claimant's stated seed and records the same fields. The verdict compares the two.

  MATCH         every checkpoint digest agrees, and both runs declare the
                determinism flags
  DRIFT         any checkpoint differs, the checkpoint counts differ, or the
                runs disagree on weights, inputs or seed
  UNVERIFIABLE  either run lacks a determinism flag, or has no checkpoints

The certificate is about replay, never about correctness. Every verdict carries
REPLAY_DOES_NOT_PROVE, and a test asserts it. Bit-exact replay is specific to
hardware and driver: a DRIFT between two devices is reported as a scope limit.

Pure data and arithmetic: this module runs nothing.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

MATCH, DRIFT, UNVERIFIABLE = "MATCH", "DRIFT", "UNVERIFIABLE"
REPLAY_DOES_NOT_PROVE = ("Same computation ran twice. Says nothing about whether the "
                         "answer is right or generalizes.")
CROSS_DEVICE_NOTE = ("The runs used different devices or drivers; bit-exact replay "
                     "across hardware is out of scope, so this DRIFT may be a scope limit.")
REQUIRED_FLAGS = ("deterministic_algorithms", "cublas_workspace_config", "cudnn_deterministic")


def state_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checkpoint_root(digests: list) -> str:
    """A Merkle-style root over the checkpoint digests, in order."""
    layer = [bytes.fromhex(d) for d in digests] or [b""]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [hashlib.sha256(layer[i] + layer[i + 1]).digest()
                 for i in range(0, len(layer), 2)]
    return hashlib.sha256(b"replay-root" + layer[0]).hexdigest()


@dataclass(frozen=True)
class RunRecord:
    weights_sha256: str
    inputs_sha256: str
    seed: int
    checkpoints: tuple
    flags: dict = field(default_factory=dict)
    device: str = ""
    driver: str = ""

    def root(self) -> str:
        return checkpoint_root(list(self.checkpoints))

    def missing_flags(self) -> list:
        return [f for f in REQUIRED_FLAGS if not self.flags.get(f)]


def _result(verdict: str, reason: str, claimed: RunRecord, replayed: RunRecord,
            divergence: int | None = None) -> dict:
    out = {"verdict": verdict, "reason": reason, "first_divergence": divergence,
           "root_claimed": claimed.root(), "root_replayed": replayed.root(),
           "checkpoints": len(claimed.checkpoints),
           "device": {"claimed": [claimed.device, claimed.driver],
                      "replayed": [replayed.device, replayed.driver]},
           "does_not_prove": [REPLAY_DOES_NOT_PROVE]}
    cross = (claimed.device, claimed.driver) != (replayed.device, replayed.driver)
    if verdict == DRIFT and cross:
        out["does_not_prove"].append(CROSS_DEVICE_NOTE)
    return out


def _identity_drift(claimed: RunRecord, replayed: RunRecord) -> str:
    for name in ("weights_sha256", "inputs_sha256", "seed"):
        if getattr(claimed, name) != getattr(replayed, name):
            return f"the runs disagree on {name}"
    return ""


def replay_verdict(claimed: RunRecord, replayed: RunRecord) -> dict:
    missing = sorted(set(claimed.missing_flags()) | set(replayed.missing_flags()))
    if missing:
        return _result(UNVERIFIABLE, f"determinism flags absent: {missing}", claimed, replayed)
    if not claimed.checkpoints or not replayed.checkpoints:
        return _result(UNVERIFIABLE, "no checkpoint digests recorded", claimed, replayed)
    identity = _identity_drift(claimed, replayed)
    if identity:
        return _result(DRIFT, identity, claimed, replayed)
    if len(claimed.checkpoints) != len(replayed.checkpoints):
        return _result(DRIFT, "checkpoint counts differ", claimed, replayed,
                       min(len(claimed.checkpoints), len(replayed.checkpoints)))
    for i, (a, b) in enumerate(zip(claimed.checkpoints, replayed.checkpoints)):
        if a != b:
            return _result(DRIFT, f"checkpoint {i} differs", claimed, replayed, i)
    return _result(MATCH, f"all {len(claimed.checkpoints)} checkpoint digests agree",
                   claimed, replayed)
