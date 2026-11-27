# Paper Citation Gate

## Overview

`harness/paper_citation_gate` verifies technical preprints and executive dossiers against live catalogue IDs and `engine-receipt/1` match proofs in pure Python stdlib under the OSI MIT license. Every document is scanned for cited catalogue IDs, em or en dashes, local Windows or Unix workstation path leaks, and affirmative corporate entity claims.

## Citation Provenance and Hygiene Rules

Calling `verify_paper_bundle` or `verify_paper_bundle_files` returns an immutable `PaperCitationReport` sealing `paper_citation_attestation_sha256` over document digests and hygiene totals. Any forged catalogue ID absent from the known live set, non-matching primary receipt, leaked local path, em or en dash, affirmative `LLC` or `Inc.` claim, or non-finite threshold fails closed while allowing explicit negated disclaimers.

## Scope Limits

This gate inspects markdown text, extracted catalogue IDs, caller-supplied receipt verdicts, and prose hygiene rules in pure Python stdlib. It does not parse PDF binaries or render visual page layouts.
