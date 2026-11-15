# Proof Surface Research Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest public research harness for measuring proof-surface packet quality.

**Architecture:** Keep the harness dependency-free and file-backed. Store cases as JSON, reuse the existing packet validator, and score each case against explicit dimensions that expose evidence quality rather than claiming truth or safety.

**Tech Stack:** Python 3.10+, stdlib JSON/argparse, existing `repo_proof_index.packet` validator.

---

### Task 1: Research cases and scorer

**Files:**
- Create: `docs/PROOF-SURFACE-RESEARCH-HARNESS-v0.1.md`
- Create: `research/proof-surface/v0.1/cases.json`
- Create: `scripts/score_proof_surface_research.py`
- Modify: `README.md`

- [ ] **Step 1: Add research-harness documentation**

Create a concise document defining the scoring dimensions:

```text
schema_valid
evidence_coverage
actionability
non_authority_language
witness_or_provenance_presence
```

- [ ] **Step 2: Add minimal cases**

Create a JSON dataset with cases for valid evidence, malformed shape, missing evidence, overclaiming language, and missing witness/provenance support.

- [ ] **Step 3: Add scorer script**

Create a stdlib script that loads cases, validates packet shape, computes dimensions, compares them to expected values, and exits nonzero on mismatch.

- [ ] **Step 4: Document command**

Add:

```bash
python scripts/score_proof_surface_research.py
```

- [ ] **Step 5: Commit**

Run file-size and scoped secret checks, then commit:

```bash
git add docs/PROOF-SURFACE-RESEARCH-HARNESS-v0.1.md research/proof-surface/v0.1/cases.json scripts/score_proof_surface_research.py README.md docs/superpowers/plans/2026-06-13-proof-surface-research-harness.md
git commit -m "repo-proof-index: add proof surface research harness"
```
