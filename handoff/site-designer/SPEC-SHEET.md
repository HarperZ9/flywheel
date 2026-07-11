# Flywheel: Spec Sheet

For the site's spec page and feature comparisons. Everything here is real today
unless the row says otherwise.

---

## What it is

A single local program that routes to any model, answers what it can verify
locally, escalates only the hard part, and hands back a re-checkable receipt for
every accepted answer. One browser surface shows all of it.

## At a glance

| | |
|---|---|
| Dependencies | None. Python standard library only. |
| Network | Fully offline for the local path. Hosted providers are opt-in. |
| Entry point | `python scripts/run_harness_cli.py app --port 8799` |
| Surface | One origin, one browser page, same-origin JSON routes |
| Local model | Flywheel-Local-Coder-14B, ~9 GB 4-bit, GPU optional |
| Accept authority | An external check. No learned model on the accept path. |
| Receipts | Content-addressed, re-checkable offline, every accepted answer |

## The routes (the one surface)

| Route | Method | What it does |
|---|---|---|
| `/site/index.html` | GET | The shell: router, world, companion, studio, demos, receipts |
| `/api/endpoints` | GET | The universal router roster, credential presence only |
| `/api/endpoints/health` | GET | Live probe of local tiers; hosted tiers report configured-or-not |
| `/api/companion` | POST | Answer locally, escalate the hard slice |
| `/api/forge` | POST | Goal into a checkable structured prompt |
| `/api/world` | GET | Root-hashed projected state |
| `/api/training/status` | GET | Read-only training status |

## The universal router

One roster of every endpoint, all feeding the same verified path:

- Local: the bundled server, Ollama, and other local servers.
- Hosted, OpenAI-compatible: the common providers.
- Native: hosted Anthropic and Gemini.
- Subscription command-line tiers.

Credentials are read as presence only, never as a value, and never written to any
receipt, ledger, or log. The differentiator over other routers: they route, this
one routes and verifies.

## Feature comparison (the wedge)

| | Ordinary router | Flywheel |
|---|---|---|
| Routes to many providers | Yes | Yes |
| One credential surface | Yes | Yes, presence only |
| Accepts on an external check | No | Yes |
| Re-checkable receipt per answer | No | Yes |
| Answers locally, escalates the hard part | No | Yes |
| Fully offline for the local path | No | Yes |
| Zero dependencies | Varies | Yes |

## Requirements

- Python 3.10 or newer. No packages to install.
- Local model: a machine that can host a ~9 GB 4-bit model, via Ollama or the
  bundled server. A GPU helps but is not required.
- Hosted providers: their API key in your environment, read as presence only.

## What is real today, and what is not yet

| Capability | State |
|---|---|
| The one surface (gateway, all routes) | Real, runs now |
| Universal router roster, presence-only credentials | Real |
| Companion seat: cache, local-verified, consensus, escalate | Real |
| Studio: goal into a checkable prompt | Real |
| Projected world, root-hashed | Real |
| Receipts on every serve route | Real |
| Training status, read-only | Real |
| The 14B local model, trained, provenance chain | Real |
| Training start and stop from the surface | Not exposed. A safety-gated action, on purpose. |
| The 32B model | No trained artifact yet. Trains when the machine is idle. |
| Capability uplift over single-shot | Not claimed. See BENCHMARKS.md. |
