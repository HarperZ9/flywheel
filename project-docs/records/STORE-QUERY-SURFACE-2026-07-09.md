# Store Query Surface - 2026-07-09

Status: implemented, not runtime-validated in this slice

## Capability

`scripts\run_harness_store_query.py` provides a zero-dependency read-only query surface over the file-backed harness store.

## What it returns

- Schema: `harness.file-store-query/v1`
- Runs
- Events
- Receipts
- Artifacts
- Totals and selected-row counts

## Commands

Query all recent store rows:

```powershell
python scripts/run_harness_store_query.py --store-root C:/tmp/harness_file_store --out C:/tmp/harness_store_query_20260709.json --markdown-out C:/tmp/harness_store_query_20260709.md
```

Query one closed-loop run:

```powershell
python scripts/run_harness_store_query.py --store-root C:/tmp/harness_file_store --run-id <run_id> --out C:/tmp/harness_store_query_<run_id>.json --markdown-out C:/tmp/harness_store_query_<run_id>.md
```

## Why this matters

The closed-loop harness no longer needs to scrape stdout to find artifacts. Runs, receipts, and artifacts are queryable from local JSONL authority before PostgreSQL, a dashboard, or a service API exists.

## Current limitation

This is a local file query surface. It is not yet a SQL adapter, API endpoint, or UI dashboard.
