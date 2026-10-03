# Override reasons and outcome checks

When the pre-action monitor holds a call, you decide: approve it once, reject it, or end the run. Each decision is a sealed record. You can now say why with a reason code, and later record whether the decision held up. Over time this shows which rules you override most, why, and whether those overrides were right.

## Give a reason when you decide

```
flywheel monitor approve <hold_id> --home <monitor home> --reason-code rule_false_positive --reason "the push goes to my own fork"
flywheel monitor reject  <hold_id> --home <monitor home> --reason-code data_destination_not_allowed
```

| Reason code | Use it when |
| :- | :- |
| `rule_false_positive` | The rule fired, but this call is fine |
| `wrong_target` | The call points at the wrong file, host or account |
| `scope_exceeded` | The call goes beyond what you asked for |
| `data_destination_not_allowed` | The call would send data somewhere it should not go |
| `needs_more_context` | You cannot tell yet and want the agent to explain first |
| `other` | None of these fit |

Both flags are optional. The code goes into the sealed decision record. The free text stays in an owner-only file in the monitor home (`reasons/<record seal>.json`), and the sealed record keeps only its SHA-256, as before. A decision without a code keeps the exact record shape it had before codes existed.

## Record the outcome later

Once you know how things turned out, link an outcome to the decision:

```
flywheel monitor outcome <decision record seal> --home <monitor home> --evidence no_harm_observed --checked-by alice
```

| Decision | Evidence | Verdict on the decision |
| :- | :- | :- |
| Approved | `no_harm_observed` | RIGHT |
| Approved | `harm_observed` | WRONG |
| Rejected or ended | `call_not_needed` | RIGHT |
| Rejected or ended | `call_was_needed` | WRONG |
| Any of these | `not_determinable` | UNKNOWN |

The verdict comes from the evidence code. You cannot type RIGHT or WRONG directly, and evidence that does not fit the decision is refused. Each decision takes one outcome; the first one stands. If the person who checks the outcome is the person who decided, the record is marked `self_check`. Expired holds take no outcome, because nobody decided them.

Like approve and reject, `outcome` needs a real terminal, and you type back the first six characters of the decision seal. An agent's shell cannot write outcomes for you.

## Read the report

```
flywheel monitor overrides --home <monitor home> [--json]
```

For each rule (or the judge) that raised holds, the report lists holds, decisions, the override rate (approvals divided by owner decisions; expiries are left out), the reason codes given, and outcomes. Outcomes checked by someone other than the decider are also counted separately as independent outcomes.

Two alarms:

- More than one owner decision in ten is coded `other`. The fixed list is missing a reason; tell us which.
- Some owner decisions carry no code.

## What it does not show

An override rate says how often you disagreed with a rule. It does not show the rule is wrong. An outcome records one person's later reading of what happened; it does not prove the decision caused the result. We have not yet measured whether two owners pick the same code for the same hold. The planned test has two owners code 50 replayed holds independently, and it passes at Cohen's kappa of 0.6 or more with no more than one decision in ten coded `other`. `coder_agreement` in `harness/preaction/overrides_report.py` computes both numbers.
