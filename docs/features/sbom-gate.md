# SPDX 2.3 and CycloneDX 1.5 Supply-Chain Gate (`harness.sbom_gate`)

`harness/sbom_gate/` validates `SPDX-2.3` and `CycloneDX 1.5` SBOM JSON documents using only the Python standard library. Every check fails closed on missing headers, invalid or unapproved SPDX license tokens, local workstation path leaks, email addresses, or raw secrets.

## Modules

`spdx_check.py` checks `SPDX-2.3` headers (`dataLicense: CC0-1.0`, `SPDXRef-DOCUMENT`, `documentNamespace`, `creationInfo`, and `relationships`), package license expression grammar, forbidden or allowed license policies, and static zero-PII leak patterns.

`cyclonedx_check.py` checks `CycloneDX 1.5` headers (`bomFormat`, `specVersion`, `urn:uuid:` serialNumber, `metadata.component`, and `dependencies`), component license entries, and the same static leak scanner.

`supply_chain_gate.py` discovers all `*.spdx.json` and `*.cdx.json` files inside a pack directory, verifies each file fail-closed, tracks unified component counts, and seals a deterministic `sbom_attestation_sha256` digest across the checked pack.

## Usage

```python
from pathlib import Path
from harness.sbom_gate import verify_sbom_pack

report = verify_sbom_pack(Path("sbom-pack"), expected_sbom_count=11)
assert report.passed
```

## Honest Scope Limits

`spdx_check.py` and `cyclonedx_check.py` validate document structure, SPDX license tokens, and static leak regexes; they do not verify detached cryptographic signatures or query external CVE feeds. `supply_chain_gate.py` audits an existing directory snapshot and does not synthesize SBOMs from package lockfiles.
