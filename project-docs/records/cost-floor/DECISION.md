# Cost receipts against the hardware floor: decision and bar

Written 2026-10-03 before the floor was computed on any recorded call.

- Decision: whether Flywheel search ships cost receipts that set measured time beside a
  speed-of-light floor, and what the docs claim about them. Owner: Flywheel search maturity sprint.
- Workload: every generation call in the effort-gate live run (G4 arms, ollama
  flywheel-local-coder-14b, Q4_K_M, 14,770,033,664 parameters, 8,988,111,146-byte weight file,
  one RTX 4090), from project-docs/records/search-effort-gate/. No new model run.
- Hardware rates: 1008 GB/s memory bandwidth and 330.3 TFLOPS dense FP16 tensor (FP16 accumulate),
  NVIDIA Ada GPU Architecture whitepaper v2.02, Appendix A.
- Bar 1 (coverage): every call with provider token counts gets a receipt with measured time,
  floor, ratio, phase bounds and the hardware source.
- Bar 2 (check the check): measured time is at or above the floor on 100% of calls. A call
  below the floor means the floor model is wrong, and the receipts do not ship as a floor.
- Reported without a target: the total and median ratio, and the share of the floor that is
  decode. The ratio is an instrument reading, so no ratio is a pass or a fail.
- Limits: measured time is wall time around one HTTP request, so it includes server and client
  overhead. The floor ignores KV-cache reads, so it is optimistic for long contexts. One model,
  one GPU.

## Correction, 2026-10-03 (after the run, before the floor was reported)

The weight-file size above, 8,988,111,146 bytes, does not match the model blob on disk, which
is 8,988,110,880 bytes (sha256-613db240...). The receipts use the measured 8,988,110,880. The
266-byte gap moves the floor by less than one part in a million. No bar changed.

## Result

Bar 1 met: 600 of 600 calls carry a receipt, with 0 untimed. Bar 2 met: 0 of 600 calls ran
below the floor. Summaries are in summary-hard.json and summary-hard_v2.json.
