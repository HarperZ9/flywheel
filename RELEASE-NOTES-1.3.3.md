# Flywheel 1.3.3

A new lane, `raw`, checks a fast lighting shortcut against ray-traced ground truth and hands you evidence a stranger can recheck from the files alone. Five Windows tests that failed now and then are fixed at their cause.

## Try it

```
pip install -U flywheel-verify
flywheel install --lanes raw
python -c "from harness import raw_lane; print(raw_lane.run({'width': 256, 'height': 256}).result.verdict())"
```

On Windows, install `Flywheel-Setup-1.3.3-x64.exe` from this release.

## The raw lane

raw runs raw-native 0.5.0, a CPU renderer with no GPU, driver or graphics API in its trust path. Each render computes ambient occlusion twice, once with a screen-space shortcut and once by ray tracing, and certifies whether the shortcut stays within an RMSE tolerance of the reference.

- **Install refuses anything unpinned.** The lane downloads the release asset for Windows x64 or Linux x64 and accepts it only when `SHA256SUMS`, the archive and the binary all match their pins. The binary is hashed again before every render. Other platforms read `TOOLCHAIN_MISSING`.
- **Three rechecks, cheapest first.** Level 1 recomputes the result from the float buffers and the mask without running anything, and reproduces the recorded RMSE bit for bit. It also holds raw-native's own `receipt.json` to the same files. Level 2 replays the render and compares every output digest. Level 3 holds another renderer's AO to raw-native's ray-traced buffer.
- **Two verdicts on every receipt.** Receipts follow the superstack contract (v0.2.0, vendored and pinned). Identity says whether the bytes match; tolerance says whether the measurement is within its bound. A replay can read DRIFT and PASS at once, and a tight tolerance can read MATCH and FAIL.

Renders from the Windows and Linux binaries replay byte-identical on both. CI runs all three levels against the real release on both platforms.

What a verdict does not prove: the reference is a 64-sample estimate, repeatable and not exact; a pass on RMSE says nothing about the worst pixel (the high view passes at 0.0827 RMSE with a 0.625 maximum error); there is one built-in scene; byte-identical output is checked on x86-64 only.

## Fewer flaky Windows tests

Five tests failed on Windows and passed on rerun. Each had a cause a retry would have hidden:

- two tests waited on a wall clock that a loaded runner could outrun;
- a self-test killed a process before it had started its child;
- the Rowan voice server answered some requests without reading their body, and Windows then reset the connection;
- the desktop goldens differed by antialiasing noise on one runner's hardware.

The first four are fixed at the cause. The goldens now accept host noise only within measured limits (channel delta 48, 8 levels outside the neighbouring pixels, 0.5 % of the frame) and still fail on a shifted, tinted or erased region. After the fix, 11 of 11 runs of each Windows test shard and 10 of 10 Windows desktop runs passed.

## Monitor rule pack

The pre-action monitor's rule pack is unchanged from 1.3.2, so a pinned
`expected_rules_digest` stays valid. `flywheel monitor owner` prints it as
`installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## Limits

- The golden noise is attributed to the runner's hardware; that is inferred, not proven.
- Other Windows tests that flaked the same day are not covered by these fixes.
- The raw lane's overhead is unmeasured, and it does not use raw-native's D3D12, WebGPU or WebAssembly builds.
