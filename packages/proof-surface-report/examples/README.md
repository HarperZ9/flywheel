# Proof Surface Report Examples

Synthetic, public example artifacts for the Markdown handoff adapter.

Render them with the installed console script:

```bash
proof-surface-report public-surface.packet.json provenance.packet.json emet.receipt.json
```

Or from a development checkout:

```bash
PYTHONPATH=../src python -m proof_surface_report public-surface.packet.json provenance.packet.json emet.receipt.json
```

The output is an evidence handoff. It is not a certification, trust verdict,
safety decision, or compliance finding.

Packet text is language-checked before rendering. Keep claims factual and
evidence-backed; do not phrase them as approval, certification, compliance, or
release safety.
