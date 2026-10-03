# Run log: live confirmation run for the search effort gate

The pre-registration is PREREG.md. Its sha256, c39ad37f1b35db96081800d31cd7228c95d9df313d5b8156854de6748ea35914,
covers the committed bytes with LF line endings. Before this branch pinned the file to LF in
.gitattributes, a Windows checkout with core.autocrlf rewrote it to CRLF, and the CRLF copy hashes
to 349ad1a8.... PREREG.md was not edited after hashing.

## Attempt 1: void

- Started 2026-10-03T19:38:18Z under D:/gpu.lock.d, ollama flywheel-local-coder-14b on 127.0.0.1:11500.
- The hard registry finished (10 rows). The hard_v2 registry had logged 90 of 110 rows when the
  host rebooted. The last row was written at 21:12Z, and processes restarted at 21:29Z. The
  server and the run died with the reboot.
- Status: VOID. No number from this attempt is reported, replayed or compared against the bar.
  A partial run would also let a reader pick which half to trust, which the pre-registration
  rules out.
- The raw files stay outside the repo for inspection, with these hashes:
  - hard.json: ebdb9de3e98d494dd628951ab91174b223a8e49c1967d0a47cf47457ca629ed8
  - hard_v2.log (partial): 1f9590c296771e5e744176bd0911c5ad9fb7fbe11c2ef2bed60c560d28bd7ae3
- The stale lock from this attempt was moved to D:/gpu.lock.stale-20261003-reboot.

## Attempt 2: the reported run

Same script (scripts/effort_gate_live.py), model, registries and seeds, rebased on main at adffc05f.
The run starts from an empty output directory and covers both registries in full. Results are in
the section below and in live-*.json beside this file.

## Attempt 2: results

Lock held 2026-10-03T21:39:48Z to 22:36:28Z. The server (PID 9976, 127.0.0.1:11500) was started
and stopped by the runner. Both registries finished with exit 0 and no excluded task.

- live-hard.json sha256 8c8c9df2682db564ddbc405663553f4f51846b31f6e567cafad7a5936439cf6b
- live-hard_v2.json sha256 80fabd3f3fec165ae0311241a852399b2a1fe3e5795a8552b7feb7077608f76a
- Replays: live-replay-first-pass.json and live-replay-sequential.json, from
  scripts/effort_gate_replay.py with the pre-registered seed and resample count.

Pass counts match G4 exactly: on hard_v2, single 61 and search 68 of 110 held-out passes (gain 7);
on hard, 9 and 9 (gain 0).

| Gate, hard_v2 (n = 110) | Retained gain | Sample ratio [95%] | Halves | Bar |
|:--|:--|:--|:--|:--|
| first-pass | 1.00 (7 of 7) | 0.509 [0.441, 0.577] | 0.523 misses, 0.496 meets | misses |
| sequential | 1.00 (7 of 7) | 0.446 [0.391, 0.502] | 0.450 and 0.441 meet | meets |

On hard, both gates draw 13 of 40 samples (0.325) and retained gain is undefined, as the
pre-registration said in advance.

Readings:

- The sequential gate meets the bar on the full set and on both halves. The upper end of its
  sample-ratio interval, 0.502, sits on the 0.50 line, so a different set of problems
  could put it over.
- The first-pass gate misses on the point estimate by 0.009. The records replay had put it at
  0.489. The gap comes from non-determinism: the temperature-0 candidate matched the single
  arm's text on 80 of 110 problems, and its visible verdict differed on 3.
- Retained gain of 1.00 rests on a gain of 7 problems, and the interval cannot resolve a loss of
  one or two.
- By construction, a gate that truncates a logged list picks what full search picks, so the
  gated and full pass counts are equal. A live gated run that redraws would see the
  non-determinism above.

Decision under the pre-registration: search ships `--effort-gate`, off by default. The docs
name `sequential` as the setting that met the bar and give the first-pass miss.
