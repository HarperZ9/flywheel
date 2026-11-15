# ai4science — wedge #8

A **scientific claim-to-experiment → proof packet**. Harvested from dogfood pass
0104 (`AI4ScienceClaimToExperimentReceipt/v1`). A portable proof layer that sits
across scientific agents, foundation models, workflow engines (Nextflow,
Snakemake), and lab-record systems — *not* "another AI scientist."

Binds a `scientific_claim` to `agent_actions`, a `protocol` + `workflow_runtime`,
a `measurement` (or its absence), a `reproduction` status, and **first-class
reviewer objections** and **negative results** (where unverified discovery claims
usually fail).

## Promotion gates (the point)
Promotion is derived conservatively and enforced on validation:
- **Reject unmeasured discovery claim** — `MEASURED`/`REPRODUCED`/`PEER_REVIEWED` require `measurement.measured == true`.
- **Require reproduction status** — `REPRODUCED`/`PEER_REVIEWED` require `reproduction.status == INDEPENDENTLY_REPRODUCED`.
- **Require human review** — `PEER_REVIEWED` is blocked by any open reviewer objection.

A single packet can never reach a promoted discovery (that needs independent review). Verdict: `MATCH` once reproduced; `DRIFT` on a negative result or failed reproduction; `UNVERIFIABLE` otherwise.

## Use

```bash
telos-proof ai4science --input claim.json --claim "..." --scope "..." --out ./artifacts
# or: python -m proof_surface.ai4science --input claim.json ...
```

`claim.json`: `{sources, domain, scientific_claim, agent_actions, protocol, measurement, reproduction, reviewer_objections, negative_result[, uncertainty]}`.
Emits `packet.json`, `report.md`, crucible `thesis`/`measurements`, an optional
peer assessment, and a content-addressed `bundle.json`.
