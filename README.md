# Flywheel

**The router and harness that verifies.** Flywheel does everything the other
routers and local runners do, plus the one thing none of them do: it checks the
answer and hands you a receipt you can re-run yourself. Point it at any model,
local or hosted, online or offline. One surface, zero dependencies.

Every other router routes. Flywheel **routes and verifies**. The authority that
accepts an answer is an external check, never a model grading its own work, and
every accepted answer carries a content-addressed receipt that a stranger can
recompute offline.

---

## Run it now

Start the one surface (the gateway) and open it in a browser:

```
python scripts/run_harness_cli.py app --port 8799
```

Then open **http://127.0.0.1:8799/site/index.html**. No packages to install.

Route a prompt to any provider you have a key for, and get a receipt with it:

```
curl -s http://127.0.0.1:8799/api/route \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "write a haiku about receipts", "endpoint": "anthropic"}'
```

Or let the companion answer it locally and escalate only the hard part:

```
curl -s http://127.0.0.1:8799/api/companion \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "write a function that returns a + 1"}'
```

**Already have an OpenAI client?** Point its base URL at the gateway. Flywheel
speaks the OpenAI API (`/v1/chat/completions`, `/v1/models`, streaming), and the
`model` field names any provider in the roster, so your existing tools route
through the verify layer with no code change:

```
curl -s http://127.0.0.1:8799/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "anthropic", "messages": [{"role": "user", "content": "say hi"}]}'
```

---

## Works with everything

One roster of every endpoint, all feeding the same verified path:

- **Local:** the bundled server, Ollama, vLLM, SGLang, LM Studio, llama.cpp.
- **Hosted, OpenAI-compatible:** OpenAI, DeepSeek, Groq, Mistral, OpenRouter,
  Together, xAI, and more.
- **Native:** hosted Anthropic and Gemini.
- **Subscription command-line tiers.**

Credentials are read as presence only, never as a value, and never written to any
receipt, ledger, or log. Bring your keys and it routes online. Bring your weights
and it runs offline, on a plane, when the network is down. The choice is yours on
every call.

---

## The one surface

Every route is same-origin JSON you can also `curl`:

| Route | What it gives you |
|---|---|
| `/site/index.html` | The shell: router, world, companion, studio, receipts, one UI |
| `GET /api/endpoints` | The universal router roster, credential presence only |
| `GET /api/endpoints/health` | Live probe of local tiers; hosted tiers report configured-or-not |
| `POST /api/route` | Route to any provider and get a receipt with the answer |
| `POST /v1/chat/completions` | Drop-in OpenAI-compatible; `model` names any provider; streams |
| `GET /v1/models` | OpenAI-compatible model list (the roster) |
| `POST /api/companion` | Answer locally, escalate only the hard slice |
| `POST /api/forge` | Turn a plain goal into a structured prompt with checkable success gates |
| `GET /api/world` | The projected state (roster, findings, cursor) under one root hash |
| `GET /api/training/status` | Read-only status of the local training run |

One line for the whole surface: every number on every page is a fetch of a
receipt file you can re-check offline.

---

## How it compares

| | Ordinary router | Local runner | Agent harness | Flywheel |
|---|---|---|---|---|
| Routes to many providers | Yes | No | Some | Yes |
| Runs a local model | No | Yes | Some | Yes |
| Works offline | No | Yes | No | Yes |
| Accepts on an external check | No | No | No | **Yes** |
| Re-checkable receipt per answer | No | No | No | **Yes** |
| Answers local, escalates the hard part | No | No | No | **Yes** |
| Goal into a checkable prompt (studio) | No | No | No | **Yes** |
| One root-hashed shared state | No | No | No | **Yes** |
| Zero dependencies, one file to run | Varies | Varies | No | **Yes** |

The columns on the left each do one job. Flywheel does all of them on one
surface, and adds the verify layer none of them have.

---

## What the companion does

Cheapest-first, on evidence:

1. **Cache hit** answers for free, and re-checks the stored answer still holds
   before serving it, so a stale answer is never returned as verified.
2. **Local, verified** runs your local model and an external check accepts it.
3. **Local, agreement** reports behavioral consensus honestly as agreement, not
   as a verified check.
4. **Escalate** happens only when the budget is spent below confidence. The
   stronger tier is named in the response, and routing to it is your call.

No learned model sits on the accept path. An external check disposes; escalation
is a confidence threshold, not a difficulty guess.

---

## What it can prove today, and what it does not claim

The model is Flywheel-Local-Coder-14B, a trained artifact with a full provenance
chain (`telos-coder-14b-cpt2020-q4_k_m.gguf`, sha256 `613db240...`).

| Arm | Hard set (10 tasks) | Wilson 95% CI | Receipts |
|---|---|---|---|
| single-shot | 8 / 10 (80%) | [0.490, 0.943] | 100% |
| verified inference | 9 / 10 (90%) | [0.596, 0.982] | 100% |
| best-of-4 | 9 / 10 (90%) | [0.596, 0.982] | 100% |
| single + oracle | 8 / 10 (80%) | [0.490, 0.943] | 100% |

Flywheel's advantages are in the product, and they are real: it routes to more
places, verifies where nothing else does, runs offline, and reproduces every
receipt. On the separate question of whether verified inference makes the *model*
measurably smarter, we do not overclaim: verified beats single-shot by +0.100
here, but the 95% interval [-0.236, +0.420] includes zero, and best-of-4 ties it.
Separating a real effect at this size needs about a hundred tasks, which is what
the curated hard lane is building toward. We show that gap on purpose. A tool that
refuses to overclaim is a tool whose other claims you can trust.

---

## The vision

Flywheel is the front surface of a verified-inference flywheel: propose with a
cheap local model, dispose with an external check, keep the re-checkable receipt,
and let what passes accumulate. The model is the replaceable half; the
verification harness is the durable half. The same discipline, an external check
that can fail plus a receipt anyone can re-run, extends from routing single calls
to composing a whole spine of accountable tools. The near-term work is widening
the verified path across every provider and growing the curated task lane until
the flywheel measurably spins. See [WALKTHROUGH.md](WALKTHROUGH.md) and
[SUPERAPP.md](SUPERAPP.md).

---

## Requirements

- Python 3.10+ (standard library only, no packages to install).
- To run the local model: a machine that can host a ~9 GB 4-bit model, via
  Ollama or the bundled server. A GPU helps but is not required.
- To reach hosted providers: their API key in your environment. Flywheel reads
  presence only, never the value.

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)**: the fastest path from zero to the running surface.
- **[WALKTHROUGH.md](WALKTHROUGH.md)**: zero to verified inference, then a tour of every route.
- **[SUPERAPP.md](SUPERAPP.md)**: the full unification spec and the increment ladder.
- **[docs/schematics/](docs/schematics/)**: architecture and verified-loop diagrams.

## License

Flywheel is released under the **Functional Source License, Version 1.1, MIT
Future License (FSL-1.1-MIT)**. Use, modify, and redistribute it for any purpose
other than building a competing product, and it converts to the MIT license two
years after each version's release. See [LICENSE](LICENSE).

## Honest boundaries

- The verifier can fail, everywhere. Every surface ships with the tamper check
  that would prove it broken. A view that cannot show drift is not shipped.
- No credentials in code, transit, receipts, or logs. Keys come from the
  environment only, as presence booleans.
- Nothing here claims a result the receipts do not support.
