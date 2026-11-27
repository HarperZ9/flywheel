# TPM Fail-Safe Protocol (`harness.fsp`)

`harness.fsp` implements a fail-closed governance, attestation, and monotonic
policy-clock protocol (`fsp`) with two explicit operational stages:

- **Stage L (`STAGE_L = "L"`)**: logging, heartbeats, attestation, monotonic
  time quorums, alert triage, and gossip audit only. Remote `throttle` and
  `halt` orders fail closed with a signed refusal (`check="stage_l"`).
- **Stage F (`STAGE_F = "F"`)**: full fail-closed enforcement once a governance
  charter activates remote throttle, halt, and lift orders under an eleven-check
  verification shim (`harness.fsp.shim`).

## Core properties verified by the suite

1. **Order before action (`shim.py`, `proofs.py`, `log.py`, `witness.py`)**:
   every order passes eleven ordered checks (canonical JSON and typed bounds,
   seat quorum and regional span, non-frontier signer on halts, inclusion across
   independent logs and operators, witness cosignatures, working-time window,
   cluster scope proof, rate limits and governed renewals, bound dependent
   notice, and replay/lift rejection). Any failure emits a signed refusal.
2. **Monotonic policy clock and anti-replay (`timesrc.py`, `devtime.py`)**:
   chained Roughtime-style queries require a device-fresh RNG nonce, two
   independent time parties within pairwise `TIME_TOL`, a monotonic time floor
   across power cycles, and a running-timer drift bound (`DRIFT_PPM`) that
   refuses forward jumps and emits signed `time-malfeasance` evidence.
3. **Heartbeat chain, silence, and split-view gossip (`device.py`, `monitor.py`, `gossip.py`)**:
   devices chain signed heartbeats with a monotonic counter and previous
   fingerprint. Counter regression or chain rollback fails the device closed at
   `boot_check`. Heartbeats carry signed log checkpoints so gossip detects
   equal-size and different-size log forks as self-contained split-view proofs.
4. **Offline stdlib verification (`crypto.py`)**: signing uses `cryptography`
   or `pynacl`, while signature verification falls back to Flywheel's
   stdlib-only `harness.ed25519_verify` and `harness.p256_verify` modules.

## Honest hardware boundary

No physical on-chip lock exists yet. On Windows machines with a TPM,
`WindowsTpmBackend` creates a non-exportable ECDSA P-256 key in the Microsoft
Platform Crypto Provider (`export_policy == 0`) and reads the monotonic clock
via `TPM2_ReadClock`. The monotonic counter, persisted time floor, and tamper
switch run in software because defining a TPM NV counter requires platform or
owner authorization held by Windows, and commodity PCs lack a wired tamper
mesh. `HONEST_HARDWARE_LIMIT` and `WindowsTpmBackend.describe()` report every
software-backed component explicitly, and the demo governs only its own child
processes.

## Running the test suite

```bash
python -m pytest -q tests/fsp
```

The suite covers all protocol invariants, Stage L and Stage F transitions,
conformance drills, and all 29 outside-review red-team attacks (replay,
rollback, clock skew, log forks, malformed bundles, crafted halts, and roster
capture) with zero skipped tests.
