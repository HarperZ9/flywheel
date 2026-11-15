# Proof Surface v0.1 Conformance Fixtures

These fixtures define the smallest shared expectations for proof-surface packet
producers and consumers.

Machine-readable fixture metadata lives in `manifest.json`.

Expected outcomes:

| Fixture | Expected |
| --- | --- |
| `valid/minimal.packet.json` | valid |
| `invalid/unknown-root-field.packet.json` | invalid |
| `invalid/bad-check-status.packet.json` | invalid |

Run with:

```bash
repo-proof-index --validate conformance/proof-surface/v0.1/valid/minimal.packet.json
repo-proof-index --validate conformance/proof-surface/v0.1/invalid/unknown-root-field.packet.json
repo-proof-index --validate conformance/proof-surface/v0.1/invalid/bad-check-status.packet.json
```

Or run the fixture set:

```bash
python scripts/check_proof_surface_conformance.py
```

These files are not authority claims. They are reproducible shape checks for a
small evidence carrier.
