# Ideas Audit Bridge

## Overview

`harness/ideas_audit_bridge` audits the 18-column `AUTHOR_IDEAS_REGISTER.tsv` accountability ledger in pure Python stdlib under the OSI MIT license. Every row is validated strictly against the register header, fixed column count, unique idea IDs, legal status values (`BUILT`, `PARTIAL`, `UNBUILT`), integer scores from 1 through 10, and zero `FLAG` cells.

## Claim-to-Receipt Parity

Calling `verify_ideas_audit` or `verify_ideas_audit_files` returns an immutable `IdeasAuditReport` partitioning every `BUILT` row into `VERIFIED_MATCH` or `UNVERIFIED` from caller-supplied catalogue IDs, receipt index entries, and live receipt match results. Any cited catalogue ID absent from the known live set is recorded under `forged_catalogue_ids` and triggers fail-closed rejection. Score parsers and ratio thresholds reject IEEE-754 `NaN`, `+Inf`, `-Inf`, and booleans disguised as integers, while sealing a deterministic `ideas_attestation_sha256` over the register digest and partition lists.

## Scope Limits

This oracle inspects schema structure, finite bounds, forged IDs, and caller-provided receipt outcomes in pure Python stdlib. It does not spawn native binaries, query remote services, or modify source TSV files.
