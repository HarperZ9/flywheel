# Open-Source Gold Standard and SBOM V3 Gate

`harness/oss_gold_sbom_gate/` is a pure-stdlib MIT verifier for the 15-repository Open-Source Gold Standard certificate and unified `SPDX-2.3` plus `CycloneDX 1.5` SBOM V3 manifest.

## Checks Performed

The oracle requires complete `15/15` repository coverage, `165/165` Gold Standard scoring, `30` SBOM JSON artifacts, and at least `259` tracked components matching manifest totals. Every repository record must carry a valid 40-character hexadecimal git commit SHA, an approved pure OSI SPDX license identifier, and valid 64-character `SHA-256` hashes for both `SPDX-2.3` and `CycloneDX 1.5` outputs.

Policy checks fail closed on any non-zero `stale_fsl_in_sboms`, `proprietary_in_sboms`, or `copyleft_in_mit_repos` counter. When on-disk verification is enabled, the gate hashes every SBOM file directly and rejects any embedded `FSL-1.1` or proprietary license string.

## Scope Limits

This gate verifies manifest integrity, license compliance, and on-disk SBOM digests. It does not query remote package registries or execute external vulnerability scanners.
