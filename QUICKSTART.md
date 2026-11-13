# Flywheel Quickstart

Flywheel routes a task to the local or hosted model and tools you choose, then
keeps a **receipt you can re-check yourself** for every accepted answer. The
current release is `1.9.0`. The browser shell below is the fallback surface, and
the native Windows app is the current user-facing client.

## Run it now

```
python -m pip install flywheel-verify
flywheel app --port 8799
```

(From a source checkout:
`python scripts/run_harness_cli.py app --port 8799`.)

The native surface is **Flywheel Desktop**. Download
`Flywheel-Setup-<version>-x64.exe` from the
[latest release](https://github.com/HarperZ9/flywheel/releases/latest) and
verify it against that release's `SHA256SUMS.txt`.
The browser shell toured below is the dev/CI fallback, served from a source
checkout (the wheel does not carry the shell's files): open
**http://127.0.0.1:8799/site/index.html**.

That starts one process, the gateway, on one origin. It serves the shell and
proxies your local model when it is up; nothing else needs to be running for the
surface to load.

## Connect a model

```
flywheel setup                                    # what is connected
flywheel setup --provider anthropic               # paste a key; it is tested, then stored
flywheel setup --provider openai --account work   # a second key under a label
flywheel auth list                                # labels per provider, * marks the active one
flywheel auth use openai work                     # switch
flywheel doctor                                   # what is still missing
```

## The gateway token

Every request to the gateway needs a bearer token, including requests from your
own machine. The gateway creates it on first start, prints its path, and keeps
it in `gateway.token` in the Flywheel home (`~/.flywheel`, or `FLYWHEEL_HOME`
when that is set). Without it a route answers
`{"error": "unauthorized", "reason": "no_token"}`. Read it into a variable once:

```
TOKEN=$(cat ~/.flywheel/gateway.token)                    # macOS, Linux, Git Bash
$TOKEN = Get-Content "$HOME\.flywheel\gateway.token"      # PowerShell
```

## The localhost surface

Every route is same-origin JSON you can also `curl` with the token:

| Route | What it gives you |
|:--|:--|
| `/site/index.html` | The fallback shell: router, world, companion, studio, receipts |
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
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "say hi", "endpoint": "anthropic"}'
```

Or ask the companion to answer locally and escalate the hard part:

```
curl -s http://127.0.0.1:8799/api/companion \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "write a function that returns a + 1"}'
```

## What the companion does, in one line

Cache hit → answer for free with the stored receipt. Otherwise run your local
model and **check** the result; agreement is reported as agreement, an external
check is reported as verified, and only the part that fails the check is
escalated to a stronger tier. The decision to escalate is a threshold on
evidence, a measured trigger, and the stronger tier is only *named* in the response,
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
capability-uplift claim. When a result is agreement with no verified check
behind it, it says so.
