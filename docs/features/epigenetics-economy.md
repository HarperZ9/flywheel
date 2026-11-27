# Model Epigenetics, Checked-Claim Economy, and Latent Handoff

`harness.epigenetics_economy` adds three zero-dependency Python stdlib verification primitives to Flywheel:

1. **Model Epigenetics (`epigenetics.py`):** Reads spectral collapse signatures directly from saved LoRA factors `(B, A)` or dense weight deltas using pure-stdlib cyclic Jacobi eigendecomposition of the symmetric Gram matrix. Computes Shannon spectral entropy `H_spec`, Roy-Vetterli effective rank `exp(H_spec)`, top-1 singular energy ratio, and Frobenius norm with zero prompts and zero inference calls, sealing each readout into a canonical SHA-256 receipt.
2. **Checked-Claim Economy (`checked_economy.py`):** Deterministic multi-agent lemma marketplace gated by an independent domain oracle and canonical SHA-256 receipts. Under ECO-001 payoff rules, verified publications earn positive credits and reuse royalties while false claims and tampered receipts trigger fail-closed rejection and economic slashing.
3. **Latent Idea-Space Handoff (`latent_handoff.py`):** 48-byte orthogonal spatial handoff codec (`4B` little-endian IEEE-754 `f32` scale, `36B` signed `int8` latent coordinates, `8B` FIPS 180-4 SHA-256 tag) matching the native BuildLang `SIG-067` kernel bit-for-bit and rejecting any 1-bit packet corruption fail-closed.

## Quick usage

```python
from harness.epigenetics_economy import (
    analyze_lora_factors,
    run_checked_claim_arena,
    seal_epigenetic_receipt,
    verify_epigenetic_receipt,
)

# 1. Zero-inference LoRA weight-spectrum forensics
sig = analyze_lora_factors(b_mat, a_mat, alpha=0.5)
receipt = seal_epigenetic_receipt("adapter-v1", sig)
assert verify_epigenetic_receipt(receipt)

# 2. 60-task multi-agent checked-claim arena
summary = run_checked_claim_arena()
assert summary["ok"]
```

## Verification

Run the standalone stdlib test suite:

```bash
pytest tests/test_epigenetics_economy.py
```

All three submodules use only the Python standard library (`dataclasses`, `hashlib`, `json`, `math`, `struct`) and emit fail-closed errors on zero-energy matrices, non-finite weights, poisoned claims, tampered receipts, and 1-bit corrupted latent packets.
