# Flywheel Superapp: Quickstart

One local program that routes to any model, local or hosted, online or offline.
It answers what it can verify locally for near-zero cost, escalates only the
genuinely hard part to a stronger model, and hands you a **receipt you can
re-check yourself** for every accepted answer. It does what every router and
runner does, plus the one thing none of them do: it checks the work. One browser
surface shows all of it. Python standard library only, zero dependencies.

## Run it now

```
python scripts/run_harness_cli.py app --port 8799
```

Then open **http://127.0.0.1:8799/site/index.html**.

That starts one process, the gateway, on one origin. It serves the shell and
proxies your local model when it is up; nothing else needs to be running for the
surface to load.

## The one surface

Every route is same-origin JSON you can also `curl`:

| Route | What it gives you |
|---|---|
| `/site/index.html` | The shell: router, world, companion, studio, receipts, one UI |
| `GET /api/endpoints` | Every provider in one roster (local and hosted), credential *presence* only, never a value |
| `GET /api/endpoints/health` | Live health of your local tiers; hosted tiers report configured-or-not |
| `POST /api/route` | Route to any provider and get a receipt with the answer |
| `POST /api/companion` | Answer a task locally, escalate only the hard slice (below) |
| `POST /api/forge` | Turn a plain goal into a structured prompt with checkable success gates |
| `GET /api/world` | The projected state (roster, findings, cursor) under one root hash |
| `GET /api/training/status` | Read-only status of the local training run |

Route to any provider you have a key for, receipt included:

```
curl -s http://127.0.0.1:8799/api/route \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "say hi", "endpoint": "anthropic"}'
```

Or ask the companion to answer locally and escalate the hard part:

```
curl -s http://127.0.0.1:8799/api/companion \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "write a function that returns a + 1"}'
```

## What the companion does, in one line

Cache hit → answer for free with the stored receipt. Otherwise run your local
model and **check** the result; agreement is reported as agreement, an external
check is reported as verified, and only the part that fails the check is
escalated to a stronger tier. The decision to escalate is a threshold on
evidence, not a guess, and the stronger tier is only *named* in the response,
never called for you.

## Why this is different from every other router

Other routers route. This one routes **and verifies**. The authority that
accepts an answer is an external check, never a model grading its own work.
Which provider served a call rides into the receipt, so provenance is part of
the record. Point it at your local model, at a local Ollama, or at any provider
you have a key for, and the same verified path runs behind all of them.

## Re-check anything

Every number the shell shows is a fetch of a receipt file. The world snapshot
carries a root hash over its parts; change one byte of any part and the hash
moves, so the snapshot is itself a receipt and the check can fail. You never
have to take the surface's word for it; recompute and compare.

## What it claims, honestly

It markets what is real: re-checkable receipts, pass-parity with the models it
routes to, availability on your own schedule, and local cost. It makes **no**
capability-uplift claim. When a result is agreement rather than a verified
check, it says so.
