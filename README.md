# Flywheel

**A companion for every model.** Bring whatever model you like, local or hosted.
Flywheel routes to it, answers what it can verify locally for near-zero cost,
escalates only the genuinely hard part to a stronger model, and hands you a
receipt you can re-check yourself for every accepted answer. One local surface
shows all of it. Python standard library only: zero dependencies, fully offline.

The differentiator over every other router (OpenRouter, LiteLLM, and the rest):
they route. This one **routes and verifies**. The authority that accepts an
answer is an external check, never a model grading its own work.

---

## Run it now

Start the one surface (the gateway) and open it in a browser:

```
python scripts/run_harness_cli.py app --port 8799
```

Then open **http://127.0.0.1:8799/site/index.html**.

Ask the companion from the command line, same origin:

```
curl -s http://127.0.0.1:8799/api/companion \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "write a function that returns a + 1"}'
```

Run the local model on its own (one file, just under 9 GB, a GPU helps but is not
required):

```
ollama create flywheel-local-coder-14b -f Modelfile
ollama run flywheel-local-coder-14b
```

---

## The one surface

Every route is same-origin JSON you can also `curl`:

| Route | What it gives you |
|---|---|
| `/site/index.html` | The shell: router, world, companion, studio, demos, receipts, one UI |
| `GET /api/endpoints` | Every provider in one roster, credential *presence* only, never a value |
| `GET /api/endpoints/health` | Live health of local tiers; hosted tiers report configured-or-not |
| `POST /api/companion` | Answer a task locally, escalate only the hard slice |
| `POST /api/forge` | Turn a plain goal into a structured prompt with checkable success gates |
| `GET /api/world` | The projected state (roster, findings, cursor) under one root hash |
| `GET /api/training/status` | Read-only status of the local training run |

One line for the whole surface: every number on every page is a fetch of a
receipt file you can re-check offline.

---

## What the companion does

Cheapest-first, on evidence:

1. **Cache hit** answers for free, and re-checks the stored answer still holds
   before serving it (never a stale serve).
2. **Local, verified** runs your local model and an external check accepts it.
3. **Local, agreement** reports behavioral consensus honestly as agreement, not
   as a verified check.
4. **Escalate** happens only when the budget is spent below confidence. The
   stronger tier is *named* in the response, never called for you.

No learned model sits on the accept path. An external check disposes; escalation
is a confidence threshold, not a difficulty guess.

---

## What it can prove today, and what it cannot yet

The model is Flywheel-Local-Coder-14B, a trained artifact with a full provenance
chain (`telos-coder-14b-cpt2020-q4_k_m.gguf`, sha256 `613db240...`). We hold
ourselves to what an outside observer can check.

| Arm | Hard set (10 tasks) | Wilson 95% CI | Receipts |
|---|---|---|---|
| single-shot | 8 / 10 (80%) | [0.490, 0.943] | 100% |
| verified inference | 9 / 10 (90%) | [0.596, 0.982] | 100% |
| best-of-4 | 9 / 10 (90%) | [0.596, 0.982] | 100% |
| single + oracle | 8 / 10 (80%) | [0.490, 0.943] | 100% |

**We do not claim a capability uplift.** Verified inference beats single-shot by
+0.100 here, but the 95% interval [-0.236, +0.420] includes zero, and plain
best-of-4 sampling ties it. So the honest, measurable claims today are 100%
receipt reproducibility, pass parity, availability on your own schedule, and
local cost. Separating a real effect at this size would take roughly a hundred
tasks, which is what the curated hard lane is building toward. The number moves
the day the evidence does, not before.

---

## Requirements

- Python 3.10+ (standard library only, no packages to install).
- To run the local model: a machine that can host a ~9 GB 4-bit model, via
  Ollama or the bundled server. A GPU helps but is not required.
- To reach hosted providers: their API key in your environment. Flywheel reads
  presence only, never the value, and never writes a key to any receipt or log.

---

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** — the fastest path from zero to the running surface.
- **[WALKTHROUGH.md](WALKTHROUGH.md)** — zero to verified inference, then a tour of every route.
- **[SUPERAPP.md](SUPERAPP.md)** — the full unification spec and the increment ladder.
- **[docs/schematics/](docs/schematics/)** — architecture and verified-loop diagrams.

---

## License

Flywheel is released under the **Functional Source License, Version 1.1, MIT
Future License (FSL-1.1-MIT)**. You may use, modify, and redistribute it for any
purpose other than building a competing product, and it converts to the MIT
license two years after each version's release. See [LICENSE](LICENSE).

## Honest boundaries

- The verifier can fail, everywhere. Every surface ships with the tamper check
  that would prove it broken. A view that cannot show drift is not shipped.
- No credentials in code, transit, receipts, or logs. Keys come from the
  environment only, as presence booleans.
- The model is the replaceable half; the verification harness is the durable
  half. Nothing here claims a result the receipts do not support.
