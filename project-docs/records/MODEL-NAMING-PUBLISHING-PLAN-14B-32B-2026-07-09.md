# 14B and 32B Naming and Publishing Plan

Date: 2026-07-09

Status type: release plan, not publish approval.

## Naming principles

Names should communicate:

- local-first operation
- accountable receipts
- agentic coding/workflow use
- model size
- release maturity

Working name family:

- `Flywheel-Local-Coder-14B`
- `Flywheel-Local-Coder-32B`

Alternative family if the release emphasizes accountability more than coding:

- `ByteWitness-Local-14B`
- `ByteWitness-Local-32B`

## Do-not-publish gates

Do not publish either model until all of these exist:

- model card
- README
- license/provenance notes
- checksum manifest
- artifact layout
- endpoint instructions
- usage examples
- benchmark summary
- safety/accountability notes
- release checklist
- endpoint profile artifact
- endpoint gate artifact
- focused agentic benchmark artifact
- limitation notes

## Release artifact layout

Recommended layout:

```text
release/
  14B/
    MODEL_CARD.md
    README.md
    LICENSE.md
    PROVENANCE.md
    CHECKSUMS.txt
    ENDPOINTS.md
    USAGE.md
    BENCHMARKS.md
    SAFETY-ACCOUNTABILITY.md
    RELEASE-CHECKLIST.md
  32B/
    MODEL_CARD.md
    README.md
    LICENSE.md
    PROVENANCE.md
    CHECKSUMS.txt
    ENDPOINTS.md
    USAGE.md
    BENCHMARKS.md
    SAFETY-ACCOUNTABILITY.md
    RELEASE-CHECKLIST.md
```

## Current publish status

Neither the 14B nor the 32B model is publish-ready in this report. The naming plan exists, but release evidence is missing until endpoint and benchmark gates run.

## Draft release scaffolds

Draft release scaffolds now exist at:

- `C:\dev\local-model\project-docs\releases\14B`
- `C:\dev\local-model\project-docs\releases\32B`

These scaffolds are blocked templates only. They do not prove model readiness, endpoint health, benchmark quality, checksum correctness, provenance, license compatibility, or publish approval.
