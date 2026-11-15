# Agent-Action Proof Packet (`proof_surface.agent_action`)

> Telemetry explains a run. A receipt justifies an action.

The rank-1 wedge: turn an agent's execution **trace** into a portable,
re-checkable **proof packet** — what was claimed, which sources it rested on,
which *material* actions ran, **why each was admitted**, their side-effect
class / idempotency / compensation, the outputs, and a
`MATCH` / `DRIFT` / `UNVERIFIABLE` verdict.

## One command

```bash
python -m proof_surface.agent_action \
  --trace examples/agent_action/trace_side_effecting.json \
  --authorization examples/agent_action/authorization.json \
  --claim "The agent wrote /work/config.json under grant grant-fs-write-work." \
  --scope "One filesystem write under /work; network excluded." \
  --packet-id demo-write --out demo-out
```

Emits into `--out`:

| File | What it is |
| --- | --- |
| `packet.json` | the unified, validated proof packet |
| `report.md` | the reviewer report (with the Trace-vs-Receipt table) |
| `crucible-thesis.json` + `crucible-measurements.json` | crucible's file contract, so an **independent** checker re-derives the verdict |

## Pipeline

```
trace ──importer──▶ actions ──builder──▶ packet ──verdicts──▶ report
                     (material          (+ admission via        (+ crucible
                      spans only)        real least-privilege    thesis/measurements
                                         check_action)           for re-derivation)
```

- **importer** — walks a normalized (OTel-shaped) span tree; side-effecting spans
  become actions, read spans become context, a side-effecting span missing its
  target is **flagged, never dropped** (fail-closed).
- **packet** — the 10-field anatomy (`claim, scope, sources, context, actions,
  admission, side_effects, outputs, verdicts, uncertainty`) in one validated
  object. Every material action must carry **exactly one** admission decision and
  **one** side-effect classification, or it does not validate — that cross-field
  invariant is what makes it a receipt, not a trace. Inherits the proof-surface
  family's two neutrality guards (no authorization-suppression field names, no
  authority-shaped language) reused verbatim from the sibling contracts.
- **builder** — admission is *derived*, not asserted: each action is run through
  proof-surface's own `authorization_receipt.check_action` against a real,
  least-privilege, expiring grant.
- **verdicts** — an embedded `verdict_for_measurement` faithful to crucible's
  pure margin rule fills the verdict layer with zero dependencies; the same
  evidence is also emitted as crucible's thesis/measurements so **real crucible**
  (`crucible-bench`) re-derives the identical verdict.

## Scope and honest boundaries

- **Zero third-party dependencies.** Stdlib only, like the rest of proof-surface.
  It does **not** import `accountable-surface` (whose runtime deps are
  undeclared), so a third party can `pip install proof-surface` and run this.
  The side-effect / idempotency / compensation fields are read from the trace as
  data — the shape an accountable actuation run produces.
- **Crucible is an optional peer.** The packet is self-contained; crucible only
  strengthens it into a sealed, re-derivable assessment when present.
- **This targets the ~10-field anatomy packet**, deliberately **not** the
  ~40-field `telos.action.receipt/v1` convention (`external_request_id`,
  `config_hash`, typed `stop_reason`, retry records, …). Those exceed what the
  current substrate can honestly populate; conforming to the richer convention is
  future work, tracked, not claimed.
