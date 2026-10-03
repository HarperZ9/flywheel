# Which lane produced a result

A Flywheel receipt can say how its result was reached. Receipt schema
`flywheel.receipt/v5` adds a `route` block to the signed claim:

- **A**: a machine re-derived the result against an independent checker.
- **H**: a person re-derived it and signs.
- **UNVERIFIABLE**: neither applies. Flywheel writes an unverifiable record
  instead of letting the result pass quietly.

```
route: {
  lane, policy_sha256, policy_version,
  inputs: { checker: yes|partial|no, checker_id, cost: low|medium|high,
            reversible, judgment, telos_tier, human_only_class },
  declared_by, reason,
  escalated_from: null | { lane: "A", trigger, at_attempt, trace_head_sha256 }
}
```

The route sits inside `claim_sha256`, so a signature covers it. Relabeling a
lane A result as lane H after signing changes the claim digest and breaks the
signature. The route stays out of `subject_sha256`, so two lanes that checked
the same thing still share a subject.

Lane A is refused when the inputs say there is no independent checker, the task
needs judgment, or its class is on the human-only list. An escalation always
leaves lane A.

Each lane adds a line to `does_not_prove`:

| Lane | Added limit |
| --- | --- |
| A | `NOT_PROVES_HUMAN_SIGN_OFF` |
| H | `NOT_PROVES_SIGNER_KEY_ROLE` (signer key roles are not checked yet) |
| UNVERIFIABLE | `NOT_PROVES_ANY_CHECK_APPLIED` |

Schema v4 stays the default and keeps its claim digest. v5 is opt-in. The router
that picks a lane and the signer key-role registry are not built yet.
