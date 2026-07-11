# Flywheel Walkthrough

From zero to verified inference, then a tour of every route on the one surface.
Everything here is same-origin. Run it fully offline against local weights, or
point it at any hosted provider you have a key for. Python standard library only.

---

## 1. Start the surface

```
python scripts/run_harness_cli.py app --port 8799
```

One process starts: the gateway, on one origin. Open the shell at
**http://127.0.0.1:8799/site/index.html**. The page loads on receipts it already
has, so it works before any model is running. When you start the local model, the
live panels (router, world, companion, studio, training) appear.

## 2. Bring a model

Any of these works. Flywheel routes to whatever is reachable.

- **Local, one file (~9 GB):**
  ```
  ollama create flywheel-local-coder-14b -f Modelfile
  ollama run flywheel-local-coder-14b
  ```
- **The bundled server** (points the gateway at a local model on port 8765).
- **A hosted provider:** put its API key in your environment. Flywheel reads
  presence only, never the value.

Check what is reachable:

```
curl -s http://127.0.0.1:8799/api/endpoints/health
```

Local tiers get a real health probe. Hosted tiers report configured-or-not, as a
boolean, never a key.

## 3. Route to any provider, with a receipt

Send a prompt to a specific provider and get its answer plus a re-checkable
receipt binding the response to the provider and model:

```
curl -s http://127.0.0.1:8799/api/route \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "say hello", "endpoint": "anthropic"}'
```

The reply carries the answer, the true `model_ref` that produced it, and a
content-addressed `receipt` you can recompute. A provider with no key present is
refused honestly, never silently answered by a different model, so the provenance
on the receipt is always true. This is the router other routers are, plus the
verify layer they are not.

## 4. Ask the companion

```
curl -s http://127.0.0.1:8799/api/companion \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "write a function that returns a + 1"}'
```

The reply names where the answer came from:

- `local-verified`: your local model ran and an external check accepted it.
- `local-consensus`: candidates agreed. This is agreement, not a verified check,
  and it is labeled that way.
- `escalate`: the local budget was spent below confidence. The response names the
  stronger tier to route to and hands back the best local attempt. It does not
  call the stronger tier for you.

Ask the same thing twice and the second answer is a cache hit, re-checked before
it is served, so a stale answer is never returned as verified.

## 5. Forge a prompt (the studio)

Turn a plain goal into a structured prompt whose success a machine can check:

```
curl -s http://127.0.0.1:8799/api/forge \
  -H 'Content-Type: application/json' \
  -d '{"goal": "parse a CSV file and pass the provided tests"}'
```

A goal with a checkable outcome scores high and lists gates an outside check can
confirm. A vague goal ("make my app better") scores low and says why. Confidence
is grounded in what a machine can verify, not in how the goal is worded.

## 6. Read the projected world

```
curl -s http://127.0.0.1:8799/api/world
```

One document that both you and the model read, carrying its own root hash over the
flagship roster, the receipt-bound findings, and the work cursor. Change one byte
of any part and the hash moves, so the snapshot is itself a receipt, and the check
can fail.

## 7. Watch the training lane (read-only)

```
curl -s http://127.0.0.1:8799/api/training/status
```

Log-derived state, the screen-liveness probe (the only thing that claims a run is
alive, so the status can never disagree with it), and checkpoint progress. This
view watches; it exposes no control that could weaken the training safety envelope.

---

## Re-check anything yourself

Every number the shell shows is a fetch of a receipt file. The receipt id is
content-addressed, so you can recompute it from its recorded parts and compare.
The verifier can fail, everywhere, which is the whole point: a pass means
something because the check that produced it could have failed.

## Where to go next

- **[README.md](README.md)**: the one-page overview and the honest benchmark table.
- **[SUPERAPP.md](SUPERAPP.md)**: the full unification spec and the increment ladder.
- **[docs/schematics/](docs/schematics/)**: the architecture and verified-loop diagrams.
