# Skill from experience: an admitted lesson plus a passing gate

Date: 2026-08-24

## The gap this closes

Lessons already existed with admission (surfaced, admitted, applied,
retired) and trace-bench already produced the evidence. What was
missing is the binding: nothing forced a skill to carry proof that its
procedure still passes today. Hermes-style skill libraries ship
procedures with vibes; this ships procedures with receipts.

## What shipped

`harness/skill_gate.py` + `/api/skills` + `POST /api/skills/bind`
(schema `flywheel.skill-gate/v1`):

1. Only an ADMITTED lesson binds. Surfaced is not yet earned; retired
   is gone. The lesson must seal-verify at bind time.
2. Evidence is a verified bench where every attempt passed, or a trace
   regression report with zero regressions over at least one task. A
   failing attempt refuses the bind -- that refusal is the teeth.
3. The binding stores digests, never payloads: lesson seal hash,
   evidence hash, task count, bound-at. verify re-derives the verdict
   from the binding's own facts and returns DRIFT on any tampering.
4. The registry persists at `<run_root>/skills/gates.jsonl`, holds
   sealed rows only, and refuses to load a tampered row rather than
   degrading silently.

## Verification

```text
python -m pytest tests/test_skill_gate.py -q                 # 6/6
python -m pytest tests/test_skill_route.py -q                # 4/4
python -m pytest tests/ -q                                   # exit 0
python scripts/check_file_gate.py                            # clean
python scripts/check_verifier_stdlib.py                      # clean
python scripts/check_claim_language.py                       # clean
```

## Does not prove

A bound gate says the procedure passed when bound; it does not prove
the claim holds beyond those tasks -- that sentence travels on every
binding's does_not_prove list. Binding checks the lesson's status and
seal but not the human judgment that admitted it; admission remains a
governance act upstream of skills.
