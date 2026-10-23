# Which lane produced a result

A Flywheel result can say how it was reached. A routed receipt
(`flywheel.routed-receipt/v1`) wraps an ordinary receipt with a `route` block:

- **A**: a machine re-derived the result against an independent checker.
- **H**: a person re-derived it and signs.
- **UNVERIFIABLE**: neither applies. Flywheel writes an unverifiable record,
  so the result carries that label wherever it goes.

```
route: {
  lane, policy_sha256, policy_version,
  inputs: { checker: yes|partial|no, checker_id, cost: low|medium|high,
            reversible, judgment, telos_tier, human_only_class },
  declared_by, reason,
  escalated_from: null | { lane: "A", trigger, at_attempt, trace_head_sha256 }
}
```

`routed_claim_sha256` covers the wrapped receipt's `claim_sha256` and the route
together. A signature over a routed result covers that digest, so relabeling a
lane A result as lane H after signing changes the digest and breaks the
signature. The wrapped receipt is unchanged: its schema, its claim digest and
every existing reader keep working.

Lane A requires an independent checker, a task that needs no judgment call, and
a class outside the human-only list; otherwise the route is refused. An
escalation always moves the result out of lane A.

Each lane adds a line to the receipt's `does_not_prove`:

| Lane | Added limit |
| --- | --- |
| A | `NOT_PROVES_HUMAN_SIGN_OFF` |
| H | `NOT_PROVES_SIGNER_KEY_ROLE` (signer key roles are not checked yet) |
| UNVERIFIABLE | `NOT_PROVES_ANY_CHECK_APPLIED` |

Today the caller declares the lane in `declared_by`. An automatic router and a signer key-role registry are planned.
