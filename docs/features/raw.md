<!-- writing-profile: readme -->
# raw (the reference renderer lane)

raw checks a fast lighting shortcut against ground truth and hands you evidence a stranger can recheck. It runs raw-native, a CPU renderer with no GPU, driver or graphics API in its trust path. Each render computes ambient occlusion twice, once with a screen-space shortcut and once by ray tracing, and writes a certificate that says whether the shortcut stays within an RMSE tolerance of the reference. Flywheel turns that certificate into a verdict and a receipt, and can recheck it three ways.

raw-native is an independent project by the same author, licensed FSL-1.1-MIT. Flywheel ships no copy of it. Installing the lane downloads the release binary from raw-native's GitHub release and refuses it unless every digest matches.

## Run it now

```sh
flywheel install --lanes raw
```

```python
from harness import raw_lane

run = raw_lane.run({"width": 256, "height": 256})
run.result.verdict()     # "PASS", "FAIL" or "UNVERIFIABLE"
run.receipt["flywheel"]  # identity MATCH or DRIFT, tolerance PASS, FAIL or UNVERIFIABLE
```

The params object is raw-native's own: `width`, `height`, `eye`, `target`, `up`, `fovy`, `tolerance`, `rt` and the `prev_*` camera for motion. A certificate's `params` field can be passed back unchanged.

## What the lane is

| Field | Value |
|---|---|
| name | `raw` |
| kind | `bundled`, served by an in-process adapter (`harness/raw_lane.py`) with no MCP server |
| version | raw-native `0.4.0` |
| organ | `perception` |
| install | fetch the release asset for this platform by URL, check it against `SHA256SUMS`, check the binary inside against a pinned SHA-256, refuse on any mismatch |
| builds | Windows x64 and Linux x64. Other platforms read `TOOLCHAIN_MISSING` |

The roster reads `missing` with `TOOLCHAIN_MISSING` until the lane is installed, and `declared` once the binary is present and still hashes to its pin. The binary is hashed again before every render, so a binary replaced after install is refused. In the desktop app the lane card reads "not in build": the app has no MCP server to start for it, and the engine's adapter starts raw-native once per render.

## Verdicts

raw-native's certificate (`raw-cert/2`, oracle `raw-rt-ao-v1`) maps to Flywheel's verdict like this:

| raw-native | Flywheel | Note carried |
|---|---|---|
| `verified` | PASS | SSAO RMSE within tolerance on covered pixels; max error is reported, not bounded |
| `refuted` | FAIL | |
| `unverifiable` | UNVERIFIABLE, reason ORACLE_UNAVAILABLE | |
| missing or malformed certificate | UNVERIFIABLE, reason ENVELOPE_MISSING | |

A render whose own files fail the level-1 recheck reads UNVERIFIABLE with ORACLE_UNAVAILABLE, never PASS.

How a run ends:

| raw-native outcome | Execution |
|---|---|
| exit 0 | COMPLETED |
| exit 1 (memory budget breached; the arena certificate is refuted) | RESOURCE_EXCEEDED, verdict FAIL |
| exit 2 (bad params) | HARNESS_ERROR |
| any other exit | CRASHED |
| binary missing, unsupported platform, or not the pinned bytes | TOOLCHAIN_MISSING |
| past the time budget (10 s plus 20 s per 512 x 512 of frame) | TIMEOUT |

## Three ways to recheck a certificate

Each level is its own check with its own verdict, cheapest first, so you can stop at the one you trust.

**Level 1, arithmetic, no execution.** Re-hash every file the certificate lists, then recompute pixel count, RMSE, maximum error and verdict from `ao_rt.pfm`, `ao_ss.pfm` and `mask.pgm` with the renderer's float32 arithmetic. It reproduces the recorded values bit for bit. A forged certificate or a tampered buffer reads FAIL. A certificate without the float buffers (raw-native 0.2.0) reads UNVERIFIABLE with ENVELOPE_MISSING. The family lives in `harness/certificates/raw_ao.py` and imports nothing that can execute.

```python
from pathlib import Path
from harness.certificates import raw_ao

files = {p.name: p.read_bytes() for p in Path("out").iterdir()}
raw_ao.verify_level1(files["certificate.json"].decode(), files).verdict()
```

**Level 2, replay.** Run the pinned binary with the certificate's recorded params and compare the new digests with the record. All equal reads MATCH. On the same platform a difference reads DRIFT, attributed to the candidate. Across platforms it reads DRIFT with the cross-device note, as a scope limit. The renders in the test fixtures, made by the Windows and the Linux binaries, replay byte-identical on both.

```python
from harness import raw_lane_replay

raw_lane_replay.replay(certificate, claimed_platform="linux-x64")["verdict"]
```

**Level 3, independent oracle.** Hold another renderer's AO, such as a GPU or browser backend, to raw-native's ray-traced buffer for the same camera. The candidate hands over canonical `ao.f32` and `mask.u8`; the checker never runs it. The bounds are the ones the superstack contract's pixel proof fixed before its first comparison: coverage mismatch at most 0.5 % of covered pixels and AO RMSE at most 0.02.

```python
from harness.certificates import raw_ao_independent

raw_ao_independent.receipt(certificate, files, candidate)["flywheel"]
```

## Receipts

Every receipt is a `superstack.receipt/1` built and sealed with the superstack contract v0.1.0, vendored byte for byte at `harness/_vendor/superstack.py` and pinned by SHA-256. Any of the contract's Python, JavaScript or C++ implementations can check the seal. Each receipt carries two verdicts side by side:

- **identity**, MATCH or DRIFT: are the bytes the reference's? For a run and for levels 1 and 2 the content is the map of output file names to SHA-256, against the map the certificate records. For level 3 it is the AO buffer itself.
- **tolerance**, PASS, FAIL or UNVERIFIABLE: is the measurement within its bound? superstack spells these `verified`, `refuted` and `unverifiable`, and the receipt's `flywheel` block repeats them in Flywheel's words.

The two can disagree, and the receipt keeps both. A replay can read DRIFT and PASS when bytes differ by less than the bound. A tight tolerance reads MATCH and FAIL: the files are exactly the recorded ones, and the shortcut misses the bound.

The `flywheel` block also records the certificate's SHA-256 in canonical JSON, the renderer version, the platform and the level's own verdict. The receipt's `params` sit in its scene, and `outputs` lists the SHA-256 of every file.

## What a verdict does not prove

Every result and every receipt lists these four lines first:

- The reference is a 64-sample hemisphere estimate from a deterministic per-pixel hash, so it is repeatable, not exact.
- A pass on RMSE says nothing about the worst pixel. The high view passes at 0.0827 RMSE with a 0.625 maximum error.
- One built-in scene; no claim about other geometry, lights or materials.
- Byte-identical output is checked on x86-64 only.

A replay adds that the same computation ran twice, which says nothing about whether the answer is right. A level-3 result adds that agreement covers one camera and frame of the built-in scene.

## Limits

- Lane overhead and the adapter's run time are unmeasured.
- raw-native ships no macOS or ARM build, so the lane reads `TOOLCHAIN_MISSING` there.
- The arena certificate's byte count differs between the Windows and Linux builds (their standard libraries allocate differently). raw-native leaves it out of the certificate's output list, so replay identity does not cover it.
- The lane uses the CPU renderer only. raw-native's WebGPU and WebAssembly builds are not wired into it.
