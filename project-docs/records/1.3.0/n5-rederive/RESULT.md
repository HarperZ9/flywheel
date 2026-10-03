# N5-full result (analyzed 2026-10-03)

Frozen files verified against PREREG.sha256 (all OK, PREREG.md 13d629a7...). `python analyze.py`
wrote results.json. 512 runs, 1.85 training GPU-hours (plan estimated about 5.5).

| Arm | False claims rejected | Established-true claims accepted |
| :-- | :-- | :-- |
| Arm 2, margin 2 x SE (0.0115) | 13/20, 0.65 [0.433, 0.819] | 13/13, 1.00 [0.772, 1.000] |
| Arm 2-sd, margin 2 x sd (0.0325) | 16/20, 0.80 [0.584, 0.919] | 11/13, 0.846 [0.578, 0.957] |
| Arm 1, rerun once | 8/20, 0.40 [0.219, 0.613] | 12/13, 0.923 [0.667, 0.986] |

Wilson 95%. 13 of 20 true candidates were established on the truth seeds; 7 were not and leave
the denominator. Baseline gate mean F1 0.7595, sd 0.0163.

Verdict: bar NOT met (needs >= 95% false rejected and >= 90% true accepted). The falsifier fires
on its first clause. `flywheel rederive` ships as preview; the notes report the numbers and say
the target was missed. The margin stays at 2 x SE: the 2 x sd arm also misses both targets on
this run, so nothing pre-registered supports a switch.

By kind, arm 2 SE: edited metric 5/5 rejected (replay UNVERIFIABLE), harmful 5/5 rejected,
dev-data 2/5 rejected, cherry-pick 1/5 rejected. Every accepted false claim is a null-effect
claim (same noise rate as the baseline, a different flip pattern) whose mean paired gain on 8
gate seeds was +0.015 to +0.039. The prereg states their true effect is zero by construction,
not by measurement. Inferred, not tested: the flip pattern itself may carry a real effect on the
test set, so some "false" claims may be true for that pattern. That reading is a hypothesis for
the next run and does not change the verdict.

Gate against rerun-once: arm 2 rejects more false claims (0.65 vs 0.40, intervals overlap at
[0.433, 0.613]); acceptance of true claims is indistinguishable.

Files here: PREREG.md and PREREG.sha256 (byte-identical to the frozen copies), claims.json,
results.json (written by analyze.py). The job builder, worker and analysis script carry local
machine paths and stay with the run; their SHA-256 values are in PREREG.sha256.
