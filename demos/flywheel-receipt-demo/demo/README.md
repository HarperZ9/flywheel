# Flywheel receipt path: a demo that proves itself

Run one command and watch a result carry its own proof. A coding task runs, the
engine emits a receipt for the outcome, and a separate process re-derives the
outcome from that receipt and returns `MATCH`. Then a forged receipt is fed to
the same checker and returns `DRIFT`, so you can see the check is real.

No API key. No GPU. No network. Python and the installed engine are all it uses.

## What you need

- Python 3.10 or newer. This demo was run on 3.12.10.
- The engine and pytest:

  ```
  pip install flywheel-verify pytest
  ```

  `flywheel-verify` is on PyPI; the current release is 1.0.0. The demo prints the
  version it finds when it starts. It was verified on 1.0.0 and on 0.3.5.

## The one command

From this folder:

```
python run_demo.py
```

It prints each step as it happens and exits `0` when the receipt path checks out.

## What the demo does, step by step

1. **Loads the task.** A small, well-defined coding task lives in `task/`. The
   task states a prompt, names its oracle (`pytest`), and gives the exact command
   that decides a pass. The oracle is the test file in `task/skeleton/`. Nothing
   in the demo can accept an answer those tests reject.

2. **Runs the task and emits a receipt.** The engine runs the oracle against a
   candidate answer and records the outcome as a proof receipt at
   `out/receipt.json`. The candidate answer is pinned in `run_demo.py` so the run
   is deterministic and needs no model. In production the candidate comes from a
   model; the accept path is identical either way, because only the oracle
   accepts.

   The verdict is one of four, not two: `PASS`, `FAIL`, `UNDECIDED` (the oracle
   ran and declined to decide), or `UNVERIFIABLE` (the oracle could not run). This
   task returns `PASS`.

3. **Shows what the receipt records.** The receipt binds the task id, the exact
   oracle command, the candidate answer, a canonical output hash, and the verdict.
   It carries no trust of its own. Everything in it re-derives from the task files
   next to it.

4. **Re-derives from the receipt, independently.** The demo runs a fresh process:

   ```
   python -m harness.verify_receipt --receipt out/receipt.json --task-dir task
   ```

   That process re-runs the oracle on the receipt's candidate and recomputes the
   hash and the verdict. When both reproduce, it prints `"verdict": "MATCH"` and
   exits `0`. `MATCH` means a stranger got the same answer offline. You can run
   this command yourself after the demo finishes.

5. **Control: forges the receipt.** The demo copies the receipt, flips the stored
   verdict from `PASS` to `FAIL`, and re-derives the forged copy. A receipt that
   could not be checked would still say `MATCH`. This one returns
   `"verdict": "DRIFT"` and exits `1`, because the recomputed `PASS` no longer
   agrees with the forged `FAIL`. The re-derivation vocabulary is `MATCH`,
   `DRIFT`, `UNVERIFIABLE`.

6. **Prints the verdict and the limit.** The honest receipt re-derives to `MATCH`;
   the forged one to `DRIFT`.

## What you will see

The headline lines from a real run:

```
verdict     : PASS          (PASS / FAIL / UNDECIDED / UNVERIFIABLE)
accepted    : True
witness     : MATCH

  honest receipt  -> MATCH
  forged receipt  -> DRIFT

RESULT: receipt path verified. Honest MATCH, forged DRIFT.
```

## Re-derive it yourself

You do not have to trust the script. After a run, `out/receipt.json` and the task
are on disk. Re-check the receipt from scratch:

```
python -m harness.verify_receipt --receipt out/receipt.json --task-dir task
```

Edit any field in `out/receipt.json`, for example change `verdict` or a byte of
the candidate, and run that command again. It will report `DRIFT`.

## What this proves, and what it does not

It proves one thing precisely: an accepted result re-derives from its receipt
offline, and a tampered result does not. That is the claim, and it is now checked
in front of you.

It does not prove the task is hard, that the answer is the best possible one, or
anything about which model wrote the answer. Those are separate questions. The
receipt path is the foundation the rest is built on: a result that cannot lie
about whether it passed its own check.

## Files in this folder

- `run_demo.py` is the one command. Runs every step above and prints it.
- `task/task.json` is the task definition (prompt, oracle, command).
- `task/skeleton/test_merge_intervals.py` is the oracle: the tests that decide.
- `out/` is created on each run; holds the receipt and the forged copy.
