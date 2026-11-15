# Proof Packet Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--proof-packet` so provenance validation results can feed the shared proof-surface interop pipeline.

**Architecture:** Keep validation unchanged. Add a CLI-layer packet formatter that converts existing per-file validation results into a neutral packet with claims, checks, and action items.

**Tech Stack:** Python 3.10+, stdlib `argparse` and `json`, existing validator module.

---

### Task 1: Add proof packet CLI output

**Files:**
- Modify: `src/model_provenance_validator/cli.py`
- Modify: `README.md`

- [ ] **Step 1: Add `--proof-packet` argument**

Add a boolean CLI flag named `--proof-packet` with help text: `Print a proof-surface interop packet as JSON.`

- [ ] **Step 2: Add packet formatter**

Add a helper that accepts the existing result dictionaries and returns:

```python
{
    "proof_surface_version": "0.1",
    "packet_id": "model-provenance-validator-batch",
    "surface": "model provenance validation",
    "status": "ready" | "blocked",
    "claims": [...],
    "checks": [...],
    "action_items": [...],
}
```

- [ ] **Step 3: Route output**

If `--proof-packet` is present, print only the packet JSON. Keep `--summary`, `--json`, and text output behavior unchanged.

- [ ] **Step 4: Document usage**

Add:

```bash
model-provenance-validator *.provenance.json --proof-packet > provenance.packet.json
repo-proof-index provenance.packet.json --summary
```

- [ ] **Step 5: Commit**

Run file-size and scoped secret checks, then commit:

```bash
git add src/model_provenance_validator/cli.py README.md docs/superpowers/plans/2026-06-13-proof-packet-output.md
git commit -m "model-provenance-validator: emit proof surface packets"
```
