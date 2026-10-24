# Which lane produced a result

A Flywheel result can say how it was reached. A routed receipt
(`flywheel.routed-receipt/v2`) wraps an ordinary receipt with a `route` block:

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

The routed receipt's `scope` is the wrapped receipt's `scope` plus one code for
the lane, naming what the route establishes:

| Lane | Added scope code |
| --- | --- |
| A | `MACHINE_REDERIVED_AGAINST_CHECKER` |
| H | `PERSON_SIGNED_ROUTE_NAMES_SIGNER` (the route records the signer it names; signer key roles arrive with lane separation) |
| UNVERIFIABLE | `NO_LANE_APPLIED_REASON_RECORDED` |

A v1 routed receipt keeps its older list name and its v1 lane codes, and it
still reads and verifies with that vocabulary.

Today the caller declares the lane in `declared_by`. An automatic router and a signer key-role registry are planned.
