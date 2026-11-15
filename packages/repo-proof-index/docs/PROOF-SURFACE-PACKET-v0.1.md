# Proof Surface Packet v0.1

Status: draft interop contract.

Purpose: carry public evidence about a technical surface without converting any
tool into an authority.

## Required object

A packet MUST be a JSON object with exactly these root fields:

- `proof_surface_version`
- `packet_id`
- `surface`
- `status`
- `claims`
- `checks`
- `action_items`

Consumers MUST reject unknown root fields for v0.1.

## Version

`proof_surface_version` MUST equal `"0.1"`.

## Identity fields

`packet_id` MUST be a non-empty string.

`surface` MUST be a non-empty string naming the public surface being described.

## Status

`status` MUST be one of:

- `ready`
- `needs-polish`
- `blocked`
- `unknown`

Status is an operational handoff label. It is not a certification, safety
verdict, authorization, or trust claim.

## Claims

`claims` MUST be an array with at least one item.

Each claim MUST be an object with exactly:

- `claim`: non-empty string
- `evidence`: non-empty string

Consumers MUST reject unknown claim fields for v0.1.

The `evidence` value SHOULD be a concise pointer, count, receipt reference, or
other reviewable statement. It SHOULD NOT contain secrets or private payloads.

## Checks

`checks` MUST be an array with at least one item.

Each check MUST be an object with exactly:

- `tool`: non-empty string
- `status`: one of `pass`, `warn`, `fail`, `unknown`
- `summary`: non-empty string

Consumers MUST reject unknown check fields for v0.1.

Check status reports the tool result only. It does not decide downstream
deployment, hiring, compliance, or safety outcomes.

## Action items

`action_items` MUST be an array of non-empty strings.

An empty array means the producer has no action item to report. It does not mean
the surface is complete or safe.

## Non-authority boundary

Packets MUST NOT claim that a system, model, repository, artifact, or release is
trusted, approved, safe, authorized, compliant, certified, or complete.

Packets carry evidence for review. Humans, owners, downstream systems, and
context-specific gates make decisions outside the packet.

## Minimal valid example

```json
{
  "proof_surface_version": "0.1",
  "packet_id": "minimal-valid-packet",
  "surface": "minimal public release surface",
  "status": "ready",
  "claims": [
    {
      "claim": "The packet has one claim.",
      "evidence": "The claim object includes claim and evidence fields."
    }
  ],
  "checks": [
    {
      "tool": "fixture",
      "status": "pass",
      "summary": "minimal packet shape is present"
    }
  ],
  "action_items": []
}
```

## Conformance

Conformance fixtures live under:

```text
conformance/proof-surface/v0.1/
```

The fixture directory includes `manifest.json` with expected outcomes.

Run:

```bash
python scripts/check_proof_surface_conformance.py
```
