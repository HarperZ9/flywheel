# Flywheel

**The one platform.** Flywheel is the single local surface that replaces the
whole category — routers, agents, harnesses, apps, and the tool family — and
closes the verified-inference loop: propose cheaply, verify with a real oracle,
keep the re-checkable receipt, and feed it back as memory, context, and catalog
for the next run. The loop, not the model, is where the correctness comes from.

The trained model (`local-model`) is one lane inside Flywheel — the replaceable
half. The flagship tools (`index`, `gather`, `crucible`, `forum`, `learn`,
`telos`) are lanes too — each an organ of the reconcile, provisioned,
health-checked, and surfaced through one gateway. Flywheel is the durable half:
the composer that binds them into one closed loop.

---

## Run it now

Start the one surface and open it in a browser:

```
flywheel app --port 8799
```

Then open **http://127.0.0.1:8799/site/index.html**. (From a checkout without
the `flywheel` command installed: `python scripts/run_harness_cli.py app --port 8799`.)

Route a prompt to any provider you have a key for, and get a receipt with it:

```
curl -s http://127.0.0.1:8799/api/route \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "write a haiku about receipts", "endpoint": "anthropic"}'
```

**Already have an OpenAI client?** Point its base URL at the gateway. Flywheel
speaks the OpenAI API (`/v1/chat/completions`, `/v1/models`, streaming), and the
`model` field names any provider in the roster.

---

## The lanes

Flywheel encompasses the tool family as lanes. Install them all, then see their
health through one surface:

```
flywheel install --lanes all       # pip + npm install the flagship family
flywheel lanes                     # roster: live / declared / missing per lane
flywheel lanes                     # → 7 lanes; gather/crucible/index/forum live, ...
```

Each lane is an organ with a role:

| Lane | Role | Organ |
|---|---|---|
| `gather` | research intake + provenance receipts | perception |
| `crucible` | falsifiable verification + re-check | verification |
| `index` | workspace map + symbol graph + verified wiki | structure (the catalog) |
| `forum` | witnessed causal ledger + routing | orchestration |
| `learn` | accountable learning forge | memory |
| `telos` | reconciliation + creative engine + doctors | reconciliation |
| `local-model` | the trained 14B proposer + the harness | propose-verify |

The lane roster is live at `GET /api/lanes` (add `?probe=true` for a live MCP
handshake with each lane). A down lane never breaks the roster; it reports
`missing` or `declared` honestly.

---

## The closed loop

Flywheel is built on one operation: **the reconcile**. Perceive a task, produce
a candidate, check it against a criterion Flywheel did not author, and carry a
receipt a third party can re-walk. The loop is closed at every altitude:

```
flywheel loop-status
# → loop closure 9/9 (100%); open: none
```

| Handoff | What closes it |
|---|---|
| perceive → propose | boot hydration (context into the prompt) |
| propose → verify | the oracle runs and disposes |
| verify → memory | accepted PASS banked in the receipt cache |
| memory → serve | a repeat is served from cache at ~0 cost |
| verify → evolve | run signals surface config candidates |
| evolve → propose | the next spin starts from an improved baseline |
| verify → corpus | verified experience enters the developmental corpus |
| **memory → context** | a verified fact feeds the next task's retrieved context |
| **corpus → model** | `flywheel corpus-export` writes a verified training shard (start is a deliberate manual step) |

Two invariants are load-bearing and never relaxed: **no receipt → no accept**,
and **no learned model sits in the accept path** — an oracle the operator names
does the deciding, never the proposer.

The folded-context → recall edge is closed too: when the agent compacts its
history, the folded span is content-addressed into a fold index so a buried
fact is recallable verbatim later instead of lost.

---

## The one surface

Every route is same-origin JSON you can also `curl`:

| Route | What it gives you |
|---|---|
| `/site/index.html` | The shell: router, world, companion, studio, receipts, lanes |
| `GET /api/endpoints` | The universal router roster, credential presence only |
| `GET /api/endpoints/health` | Live probe of local tiers; hosted tiers report configured-or-not |
| `GET /api/lanes` | The lane roster — live / declared / missing per flagship lane |
| `POST /api/route` | Route to any provider and get a receipt with the answer |
| `POST /api/agent` | Run a gated, witnessed tool loop (read/edit/run) over any provider |
| `POST /v1/chat/completions` | Drop-in OpenAI-compatible; `model` names any provider; streams |
| `GET /v1/models` | OpenAI-compatible model list (the roster) |
| `POST /v1/embeddings` | OpenAI-compatible embeddings, routed to a provider by name |
| `POST /api/companion` | Answer locally, escalate only the hard slice |
| `POST /api/forge` | Turn a plain goal into a structured prompt with checkable success gates |
| `GET /api/world` | The projected state (roster, lanes, findings, cursor) under one root hash |
| `GET /api/receipts` | The receipts ledger: the re-hashed catalog plus accepted proof envelopes |
| `GET /api/profiles` | Profile manifests (code, design, work, cowork, chat) over the one substrate |
| `GET /api/workflows` | Staged workflow definitions plus recent persisted runs |
| `POST /api/workflow` | Run a staged workflow over any endpoint; one chained receipt per run |
| `GET /api/memory` | Durable memory stats (content-addressed fold index) |
| `POST /api/memory/recall` | Verbatim recall with span-hash provenance |
| `POST /api/memory/note` | Keep a durable content-addressed note |
| `GET /api/router/stats` | Observed per-provider success rate, latency, and cost score |
| `GET /api/uplift` | Bare-vs-wrapped uplift bench runs: per-arm intervals, honest nulls kept |
| `GET /api/graph` | The cross-surface knowledge graph; `?budget=&q=` returns a priced context plan |
| `GET /api/credo` | The belief, content-addressed, with the long-form essay URL |
| `GET /api/readiness` | Release readiness per tool, measured not felt; gaps named |
| `POST /api/attest` | Ownership made checkable: a sign-off carrying its review coverage |
| `POST /api/explain` | The teach-back as a receipt: mechanical engagement gate over a diff |
| `POST /api/lean` | The apex oracle: the Lean kernel decides, the proof is the receipt |
| `POST /api/invent` | Generation under witness: propose conjectures the corpus lacks, kernel judges, survivors chain |
| `GET/POST /api/tension` | Measurement-tension ledger: two frozen-source measurements, one honest verdict |
| `GET/POST /api/retention` | What is still held vs once shown: due retests, unaided outcomes banked |
| `GET /api/comprehension` | Per-file ownership from checked evidence, not git blame |
| `POST /api/science` | Evidence intake, a gated research spec, witnessed claim verdicts, one chain |
| `GET /api/training/status` | Read-only status of the local training run |

One line for the whole surface: every number on every page is a fetch of a
receipt file you can re-check offline.

---

## Works with everything

One roster of every endpoint, all feeding the same verified path:

- **Local:** the bundled server, Ollama, vLLM, SGLang, LM Studio, llama.cpp.
- **Hosted, OpenAI-compatible:** OpenAI, DeepSeek, Groq, Mistral, OpenRouter,
  Together, xAI, and more.
- **Native:** hosted Anthropic and Gemini.
- **Subscription command-line tiers.**

Credentials are read as presence only, never as a value, and never written to
any receipt, ledger, or log. Bring your keys and it routes online. Bring your
weights and it runs offline.

---

## What the companion does

Cheapest-first, on evidence:

1. **Cache hit** answers for free, and re-checks the stored answer still holds
   before serving it.
2. **Local, verified** runs your local model and an external check accepts it.
3. **Local, agreement** reports behavioral consensus honestly as agreement.
4. **Escalate** happens only when the budget is spent below confidence.

No learned model sits on the accept path. An external check disposes;
escalation is a confidence threshold, not a difficulty guess.

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

Flywheel's advantages are in the platform, and they are real: it routes to more
places, verifies where nothing else does, runs offline, closes the loop, and
reproduces every receipt. On the separate question of whether verified inference
makes the *model* measurably smarter, we do not overclaim: verified beats
single-shot by +0.100 here, but the 95% interval includes zero. A tool that
refuses to overclaim is a tool whose other claims you can trust.

---

## Requirements

- Python 3.10+ (standard library only, no packages to install for the core).
- To run the local model: a machine that can host a ~9 GB 4-bit model, via
  Ollama or the bundled server. A GPU helps but is not required.
- To reach hosted providers: their API key in your environment.
- To install the lanes: `pip` and `npm` on PATH.

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)**: the fastest path from zero to the running surface.
- **[WALKTHROUGH.md](WALKTHROUGH.md)**: zero to verified inference, then a tour of every route.
- **[PROJECT.md](PROJECT.md)**: the verified-inference harness architecture and layer map.
- **[SUPERAPP.md](SUPERAPP.md)**: the unification spec and the increment ladder.
- **[VERIFIED-DATA-FLYWHEEL.md](VERIFIED-DATA-FLYWHEEL.md)**: the systems-efficiency thesis the loop embodies.

## License

Flywheel is released under the **Functional Source License, Version 1.1, MIT
Future License (FSL-1.1-MIT)**. Use, modify, and redistribute it for any purpose
other than building a competing product, and it converts to the MIT license two
years after each version's release. See [LICENSE](LICENSE).

## What this believes

One belief across every surface, kept as a content-addressed artifact
([CREDO.md](CREDO.md), served live at `GET /api/credo`): knowledge open to
anyone who can attain the means, and we build to lower the means; acceptance
decided by external checks, never reputation; every result re-runnable;
honest nulls first-class; ownership earned by comprehension; learning woven
into the work. The long form is
[The Unbundling](docs/essays/2026-07-13-the-unbundling.md).

## Honest boundaries

- The verifier can fail, everywhere. Every surface ships with the tamper check
  that would prove it broken.
- No credentials in code, transit, receipts, or logs. Keys come from the
  environment only, as presence booleans.
- Nothing here claims a result the receipts do not support.
- The `corpus → model` trigger is a deliberate manual step by design: the export
  path is wired, but training never auto-starts.
