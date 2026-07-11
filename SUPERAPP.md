# Flywheel Superapp: the One Surface

> Unification spec. Synthesizes the operator vision with the six-reader survey
> (showcase, packaged-app, companion, endpoints, training, projected-world).
> Spec only. Nothing here is committed, published, or launched by this document.

Last updated: 2026-07-09. Source commit context: ff8b781 (packaged), af5feda (showcase).

---

## 1. What the superapp is

The operator vision, verbatim and binding: "All of the final 3 should be one,
large interoperable surface. The harness works with local and enterprise
models, all endpoints, and also trains models, and establishes the projected
world for both the person and the model to operate within." The superapp is
that one surface: the companion positioning (the routing-and-caching seat
between any harness and any model), the packaged local-harness application
(the distributable binary plus its 32-command receipt fleet and the offline
agent), and the application showcase (the offline, theme-aware shell) fused
into a single program with a single entry point. It talks to the trained local
14B, to Ollama, and to every enterprise endpoint through one adapter layer; it
starts, watches, and stops the RAM-gated 32B training lane without weakening
its safety envelope; and it renders the projected world, the
criterion-conserving image of the whole system's state that the person and the
model perceive identically because both re-derive it instead of trusting a
report. The local model remains the replaceable half. The superapp is the
durable half. Every accepted action carries a re-checkable receipt, and the
checker can fail.

## 2. The one surface

### The merge

The three "final 3" pieces are not three apps. They are three roles of one app:

| Piece | Becomes | How |
|---|---|---|
| Application showcase (`site/index.html`) | The **shell**: the live UI of the running app | Stops being hand-transcribed marketing; fetches the same receipt JSON the CLI emits, gains views for endpoints, world, training, demos, registry |
| Packaged local-harness app (`artifacts/exe/packages/...`) | The **distribution**: how the one surface ships | `local-harness.exe` gains an `app` subcommand; the existing build → emit-contracts → bundle → hash → ship-doctor pipeline packages the shell and gateway alongside the CLI and agent |
| Companion positioning (`project-docs/COMPANION.md`) | The **seat**: the routing/caching middle the surface occupies | The gateway exposes the companion endpoint: verified-sub-result cache hits answered locally with receipts, oracle-checked local attempts first, escalation to the expensive tier only on oracle failure |

### The single entry point

**`local-harness app`** (from the packaged exe or `python scripts/run_harness_cli.py app`
from a checkout). It starts one process, the **gateway** (`harness/gateway.py`,
NEW, stdlib `ThreadingHTTPServer`), on one origin (default `127.0.0.1:8791`,
the port `.claude/launch.json` already reserves for `flywheel-site`), serving:

- **Static**: `site/` (the shell), `demos/` (players + transcripts), `artifacts/` (receipts). This is exactly what `python -m http.server 8791` does today, so the shell works before any API exists.
- **Proxy**: `/generate`, `/chat/completions`, `/v1/messages` forwarded to `harness/serve.py` on `127.0.0.1:8765` when it is up. Single origin means no CORS surgery on serve.py.
- **APIs** (all GET, read-only, JSON, each a versioned `harness.*/v1` schema): `/api/world`, `/api/endpoints/health`, `/api/training/status`, `/api/demos`, `/api/manifest`, `/api/receipts`.
- **Gated actions** (POST, explicit allowlist, never implicit command execution): receipt re-runs from the safe subset of the 32-command fleet, training start/graceful-stop behind operator confirmation. Anything not on the allowlist is CLI-only.

One doorway line for the whole surface: every number on every page is a fetch
of a receipt file you can re-check offline.

## 3. Subsystem map

Convention: REUSED entries are exact existing paths, used as-is or extended in
place. NEW entries are stdlib-only modules or files that do not exist yet.

### (a) Endpoints: local Ollama/GGUF + serve.py + enterprise APIs, receipt-pinned

REUSED
- `C:\dev\local-model\harness\serve.py`: local HF serve (14B/32B nf4, LoRA via `SERVE_ADAPTER_PATH`), routes `/generate`, `/chat/completions`, `/v1/messages`, port 8765.
- `C:\dev\local-model\harness\messages_api.py`: `make_receipt` (content-addressed request⊕prompt⊕model⊕response), `resolve_model` tier-aliasing, `X-Receipt-Id`.
- `C:\dev\local-model\harness\endpoints.py`: the superset multi-endpoint ladder (plan/api/provider/cloud; OpenAI-compat, Anthropic, Gemini, CLI, OpenCode backends; injectable transport). Canonical over the diverged relay copy.
- `C:\dev\local-model\harness\providers.py`: fail-closed 14-entry provider registry pinning `model_ref="provider:model"` into every envelope and cache key.
- `C:\dev\local-model\harness\proposer.py`: the Proposer seam that keeps the oracle/witness accept path identical regardless of who proposed.
- `C:\dev\local-model\harness\local_agent.py` + `local_agent_cli.py`: offline agent with ServeBackend → OllamaBackend failover and uniform per-turn receipts in `_finalize`.
- `C:\dev\local-model\harness\model_profiles.py`: the weights identity registry (14B GGUF `artifact_sha256 613db240...`, 32B `trained:False` guard).
- `C:\dev\local-model\harness\local_session.py`: hash-chained tamper-evident session ledger (`Entry.prev_hash`, `verify()`, head-hash root).
- `C:\dev\local-model\harness\cache.py` + `proof_cache.py`: verified-result receipt cache (input-addressed) and proof-addressed memory (fact-addressed).
- `C:\dev\local-model\harness\escalation.py`: tiered cheap-to-expensive gating pattern (currently oracle tiers).

NEW
- `harness/endpoint_registry.py`: one adapter layer over both abstractions: a Backend→Proposer bridge so `endpoints.py` backends (Anthropic, Gemini, CLI tiers) can feed the oracle/witness accept path that today only `providers.py` reaches; one roster enumerating every endpoint (serve 14B/32B, ollama, plan/max CLI, api, provider, cloud, opencode) with per-endpoint receipt capability and credential-presence booleans (env presence only, never values).
- Receipt uniformity in `serve.py`: mint the same `make_receipt` on `/chat/completions` and `/generate` (today only `/v1/messages` has it), and bind `model_profiles.artifact_sha256` into the receipt so a receipt proves WHICH weights served it.
- Ledger-everything: append every endpoint call, including EnterpriseProposer calls, into a `SessionLedger` chain (today only agent turns chain).
- Gemini key fix in `harness/endpoints.py` (~line 149): move the API key from the URL query string to the `x-goog-api-key` header.
- `harness/selector.py` + `harness/adaptive_select.py` (BUILT 2026-07-10): the selection+escalation CORE the seat mounts on. `select()` prefers the external oracle (highest trust, the measured 23% arm), falls back to deterministic behavioral consensus with an honest confidence gate, and emits a re-checkable `SelectionReceipt`. `AdaptiveSelector` implements the measured lever: generate → select → RAISE N (double the candidate budget) → escalate only when budget is exhausted below confidence. Escalation is a pure confidence threshold, not a learned difficulty predictor; no learned authority enters the accept path.
- `harness/companion.py` (remaining): the thin wrapper that adds the proof-cache lookup and the chained-ledger routing record around the selection core above. Proof-cache hit → answer locally; miss → `AdaptiveSelector.select()`; its ESCALATE verdict (not a guess) is what routes to the frontier tier.
- `harness/findings.py` (BUILT 2026-07-10): the receipt-bound findings composer -- scans run artifacts, binds every metric to a source hash, emits a root-hashed `flywheel.findings/v1` doc with honest "pending" for incomplete runs. The seat and shell render it; `verify_findings` detects staleness.

### (b) Training lane: safe operable wrapper honoring RAM gates and STOP flags

REUSED (the safety envelope is untouched; the wrapper shells it verbatim)
- `C:\dev\local-model\scripts\launch_32b_training.ps1`: Windows entry: STOP-flag clearing, RAM advisory, detached WSL `screen` session `train32b`.
- `C:\dev\local-model\scripts\run_phase2_32b_supervised.sh`: 22 GB MemAvailable gate (120 s poll, 24 h timeout), STOP flag between attempts, 12-attempt bounded auto-resume.
- `C:\dev\local-model\scripts\run_phase2_linux.sh`: offline env (`HF_HUB_OFFLINE=1`, caches on /mnt/e), `MODEL_SIZE` switch.
- `C:\dev\local-model\train\qlora_cpt.py`: `--smoke` 2-step VRAM preflight (the UI's dry-run button), `--resume`, `--save-steps 50`.
- `C:\dev\local-model\dataset\receipt.py`: `build_receipt`/`verify_receipt` (5-layer hash chain, MATCH/DRIFT/UNVERIFIABLE).
- `C:\dev\local-model\dataset\corpus_manifest.py`: fail-closed safety gate (`SAFETY_DENY_SEGMENTS`).
- Path contract (treat as API): STOP flag `E:\local-model-run\STOP_32B`, logs `E:\local-model-run\logs\phase2-32b-supervisor.log` and `phase2-linux-32b-full.log`, checkpoints `E:\local-model-run\checkpoints\phase2-linux-qlora-cpt-32b`, screen name `train32b`. Everything large stays on E:, per hardware doctrine.
- `C:\dev\local-model\project-docs\TRAINING-32B.md`: the operator doc (note: it lives under project-docs, not repo root).

NEW
- `harness/training_lane.py`: read-only status: parse the supervisor log's regex-stable lines ("RAM gate waiting/open", "attempt N/12", "training completed with rc=0"), `wsl screen -ls` liveness, latest `checkpoint-*/trainer_state.json` step vs the ~2,019-step target; emit `harness.training-status/v1` with states `stopped | waiting-for-RAM | training | completed | gave-up`. Includes the E:\ ↔ /mnt/e path translator.
- Double-launch guard: refuse start when `wsl screen -ls` already shows `train32b` (plus a lock file at `E:\local-model-run\train32b.lock`). Today nothing prevents two supervisors contending for one checkpoint dir.
- Gated controls: **start** shells `launch_32b_training.ps1` unmodified after the guard; **graceful stop** creates `STOP_32B` and the UI states honestly that it takes effect between attempts, not mid-step; **hard stop** (kill the WSL python) is a separate, separately confirmed action.
- Post-training receipt action: a thin CLI/action invoking `dataset/receipt.py` build + verify, since the training path never writes one today.
- Deliberately absent, forever: any RAM-gate bypass, any recipe override (seq_len 256 / epochs 0.25 are recipe-parity constraints on a 32 GB box), any control that weakens the supervisor. The wrapper exposes zero knobs the supervisor does not already have.

### (c) The projected world: shared live state both person and model read

The reading is already latent in `SUPERPROJECT.md`: the forward direction of
the reconcile "is a projection (conserve the criterion, discard the rest)".
The projected world is the criterion-conserving image of the system's state:
exactly the subset both parties can perceive identically because both
re-derive it.

REUSED (the five layers that exist)
- Geography: `C:\dev\local-model\harness\superproject.py`: `MANIFEST`/`roster()`/`spine()`/`probe_live()`; paired with `SUPERPROJECT.md` (the human/machine two-view duality to generalize).
- Facts: `C:\dev\local-model\harness\envelope.py` (ProofEnvelope, the atomic world-fact) re-checked by `harness\witness.py` (MATCH/DRIFT/UNVERIFIABLE), persisted in `harness\cache.py` + `harness\proof_cache.py`.
- Beliefs: `C:\dev\local-model\harness\wiki.py` (sealed, content-addressed KnowledgeBase) + `harness\second_brain.py` (witnessed write-back that refuses ungrounded notes).
- Change-feed: `C:\dev\local-model\harness\knowledge_monitor.py`: transition-only subscriptions (fires on verdict CHANGE, never steady state); the anti-noise discipline a shared world needs.
- Time/cursor: `C:\dev\local-model\STATE.md` (append-only, newest-first) + `harness\boot.py` (hydration packet, `root_hash` freshness gate to UNVERIFIABLE); the model's entry point into the world.
- Design ground: `C:\dev\local-model\MEMORY-SUBSTRATE.md` layers 3-5 (one artifact, three uses: cache = training data = receipts).

NEW
- `harness/world.py`: the composer that does not exist: `project_world()` returns one `harness.projected-world/v1` document joining (1) spine roster with optional live-probe health, (2) a single content-addressed receipt catalog scanning envelope dirs, ReceiptCache, proof_cache, and `artifacts/*.json` (today four disjoint stores with no index), (3) freshness verdicts from a persisted monitor state, (4) the cursor. The composite carries its own root hash; `verify_world()` recomputes it, so the world snapshot is itself a receipt and the check can fail.
- Persisted monitor state: a JSONL last-verdict store so `knowledge_monitor` transitions survive sessions, plus snapshot diffing ("projected world at T1 vs T2, what changed") since both snapshots are content-addressed.
- Cursor machine-twin: generate `state.json` beside `STATE.md` (head entry, timestamp, content hash). The cursor stops being bytes the model merely hashes and becomes checked state; drift between twin and prose collapses to UNVERIFIABLE.
- Consumption is symmetric: the model reads the world through an extended boot packet (`boot.py` gains the world root_hash as a SourceRef); the person reads the identical document through the shell's World view. Neither gets a private version.

### (d) The shell/UI: offline, theme-aware, zero-dep

REUSED
- `C:\dev\local-model\site\index.html`: the full CSS token system (10 custom properties, light/dark via `prefers-color-scheme` + `:root[data-theme]` override) and components (.tile, .status .s, .bench, .note, .cta); lines 236-248, the theme-toggle IIFE with `localStorage('fw-theme')`.
- `C:\dev\local-model\scripts\demo_player_html.py`: `render_player_html()`: the self-contained offline terminal player; its typewriter renderer gets lifted so the shell can display any `harness.demo-transcript/v1` payload.
- `C:\dev\local-model\scripts\demo_recorder.py` + `demos\<name>\transcript.json` (10 dirs) + `demos\scripts\*.json`: the evidence media type and its seed content.
- `C:\dev\local-model\scripts\run_harness_cli.py` `build_manifest` + `render_registry_html` (~line 530): the 31-command machine-readable command table: the shell's Registry view data model.
- `C:\dev\local-model\.claude\launch.json`: the `flywheel-site` single-origin config the gateway inherits.
- `C:\dev\local-model\artifacts\exe\*.local.json` + `artifacts\flywheel-local-coder-14b-benchmark-ci.json`: the receipts the shell renders instead of hand-typed numbers.

NEW
- `site/assets/tokens.css` + `site/assets/app.js`: factor the one token set; converge the three divergent inline palettes (site page, player template, registry renderer) on it.
- Data layer: fetch the artifact JSONs above; every rendered number carries its source path and a staleness badge (receipt timestamp vs now, a signal no page surfaces today).
- `demos/index.json`: generated manifest (emitter hook in `demo_recorder.py`); the gallery enumerates instead of hardcoding 10 anchors.
- Hash-based client routing, zero-dep: views for Home (feature-first), Endpoints, World, Training, Demos, Registry, Receipt-detail. Feature-first per doctrine; accountability is one doorway line on Home, not the organizing lens.
- In-browser re-verification: `SubtleCrypto.digest` recomputes transcript `output_sha256`/`receipt_sha256` and the world `root_hash`; badge MATCH/DRIFT. The "anyone can re-check" claim stops being CLI-only, and the browser verifier can visibly fail.
- Tests: stdlib tests asserting the shell's data contract (rendered numbers == receipt JSON fields, manifest covers every `demos/*/transcript.json`); today `tests/` covers none of `site/` or the players.

## 4. Increment ladder

Each increment ships alone, behind nothing, and states the observation that
would prove it broken.

**Increment 1: the shell goes live on receipts it already has** (one session).
Build `demos/index.json` generation, add the shell data layer fetching
`artifacts/flywheel-local-coder-14b-benchmark-ci.json` and
`artifacts/exe/model_release_readiness.local.json` /
`model_endpoint_gate.local.json` to replace every hand-typed number, add
staleness badges. Served by the existing `flywheel-site` launch config; no
backend work. *Falsifier:* change one Wilson-CI value in the benchmark JSON
and reload; if the page still shows the old hand-typed number, increment 1 is
broken. Drop a new `demos/<name>/transcript.json` and regenerate; if the
gallery does not show it, broken.

**Increment 2: one gateway, one origin, one entry point. SHIPPED 2026-07-10.**
`harness/gateway.py` (zero-dep stdlib server) plus the `app` subcommand in
`run_harness_cli.py` (`harness app --port 8799`): same-origin static serving of
the shell/demos/artifacts, proxy of `/v1/*` + `/generate` + `/health` to
serve.py:8765, `/api/endpoints/health` (local tiers get a live probe;
enterprise providers report a credential-present BOOLEAN from `endpoints.py`'s
`PROVIDERS`, never a value), and `/api/world` v0 (spine roster + receipt catalog
with a sha256 root hash over the cataloged files). Both falsifiers hold: a down
local endpoint reads unhealthy (probe fails closed), and touching a cataloged
receipt moves the root hash (6 gateway tests + the two falsifiers, live-smoked:
serve+ollama healthy, no key value leaked, shell served 200). *Original
falsifier spec:* kill serve.py -> the 14B tier must flip unhealthy; tamper a
receipt byte -> root_hash must change.

**Increment 3: receipts uniform across every endpoint.** The ROSTER + BRIDGE half
is BUILT (`harness/endpoint_registry.py`, 2026-07-11, 7/7 tests): `unified_roster()`
enumerates all 20 endpoints (14 OpenAI-compat providers + local serve/ollama/vllm/
sglang/lmstudio/llamacpp + native Anthropic/Gemini + claude/codex CLI tiers) with
credential-PRESENCE booleans (never a value), and `BackendProposer` bridges any
native backend into a verified Proposer so EVERY endpoint feeds the same oracle+
witness+receipt path -- provider provenance rides `model_ref` into the receipt.
Two more parts DONE 2026-07-11: (a) the Gemini key moved OUT of the URL query
string into the `x-goog-api-key` HEADER (a query-string key leaks into access
logs / proxy logs / history; a falsifier asserts a canary key value never appears
in the request URL and does appear in the header). (b) `LedgeredProposer` in
`endpoint_registry.py` chains EVERY endpoint call -- serve, OpenAI-compat, native
Anthropic/Gemini, CLI, or the enterprise bridge -- into one tamper-evident
`SessionLedger`: each entry commits to `(endpoint, model_ref, seed, prompt_sha,
response_sha)`, never the prompt/response TEXT and never a key; `make_endpoint_
proposer(..., ledger=...)` opts any endpoint into it. Falsifiers hold: flip one
byte of a recorded entry and `verify()` fails; a prompt canary never appears in
the serialized ledger. STILL DEFERRED (needs the live model to verify end to
end): mint `make_receipt` on serve's `/chat/completions` and `/generate` and bind
`artifact_sha256` from `model_profiles.py` into those receipts. *Deferred-part
falsifier:* recompute a `/chat/completions` receipt_id from its recorded parts;
mismatch means broken. Serve a different GGUF; if the receipt's weights hash does
not change, broken.

**Increment 4: the training lane in the shell, safety intact. STATUS HALF SHIPPED
2026-07-11.** `harness/training_lane.py` (read-only) + `GET /api/training/status`
are built and live: the status doc composes the log-derived `state`
(stopped|waiting-for-RAM|training|completed|gave-up|unknown, parsed from the
supervisor's own regex-stable lines), the screen-liveness probe, and checkpoint
progress vs the 2,019-step target. The subsystem falsifier holds BY CONSTRUCTION:
liveness is the `wsl screen -ls` probe and ONLY that probe (`screen_alive`), so the
status can never disagree with screen about whether the run is alive; the
log-derived `state` is a separate descriptor and a divergence sets `reconciled=
False` (e.g. an in-flight attempt with a dead screen -> crashed without a terminal
line). The `would_double_launch` guard is built and pure (refuses when a screen is
alive OR unprobed OR the lock exists -- fail safe). 19 falsifier tests + 1 gateway
route test; live-smoked (no run -> honest `stopped`, no crash). DELIBERATELY
DEFERRED as an operator-gated surface, NOT built here: the start / graceful-stop /
hard-stop ACTIONS and the post-training receipt action. Building status-only first
honors the ordering rationale -- the most dangerous subsystem exposes read-only
truth before any control. *Action-half falsifiers (when built):* issue start twice
-> a second `train32b` supervisor must be refused; create STOP_32B via the shell
during a RAM-wait -> the supervisor log must record the stop; any exposed parameter
that can lower the 22 GB gate or alter seq_len/epochs is broken by design review.

**Increment 5: the companion seat. SHIPPED 2026-07-11.** The selection+escalation
CORE was built and measured (`harness/selector.py`, `harness/adaptive_select.py`,
2026-07-10); `harness/companion.py` (2026-07-11) is the routing seat on top of it,
and it is wired behind the gateway at `POST /api/companion`. Cheapest-first: a
proof-cache hit answers at ~0 cost with the stored receipt; a miss goes to
`AdaptiveSelector.select()` over the local 14B (`ServeProposer`); only an ESCALATE
verdict (budget exhausted below confidence -- a threshold, not a learned guess)
NAMES the frontier tier in `escalate_to`, never calling it inline. Only an
oracle-verified `PASS` (`local-verified`) is written to the cache; a
`CONSENSUS_PASS` (`local-consensus`) is flagged as agreement, not verification, and
never cached. The gateway holds ONE seat for its lifetime so the cache and routing
ledger accumulate across requests. *Falsifiers, both live:* a cached fact answers
`source=cache` with no `escalate` row in the ledger (no frontier call); a local
failure escalates with `text=None`, `escalate_to` named, `best_effort_text`
preserved, and the ledgered failed-local `SelectionReceipt` (`verdict=ESCALATE`,
`candidates_used>0`) as the evidence preceding it. 9/9 companion falsifiers + 3
gateway companion falsifiers; live-smoked over the wire (serve down -> honest
escalate, no crash; `/api/world` root-hashed; `/api/endpoints` 20/9). What remains
is the OPTIONAL MCP-tool edge and, from increment 3, per-endpoint receipt minting
on the serve routes (so a `local-verified` cache entry carries a weights-bound
receipt end to end).

Ordering rationale: 1 needs no new backend and makes drift impossible on day
one; 2 creates the entry point everything else mounts on; 3 makes the receipt
story uniform before the seat depends on it; 4 is high-value but touches the
most dangerous subsystem, so it waits for the gateway's gating pattern to be
proven; 5 is the positioning promise and needs 2+3 underneath it.

## 5. Honest boundaries

What the superapp is NOT, and the gates that stay closed:

- **Not an auto-publisher.** HF upload remains dry-run staged
  (`huggingface_release_stage.local.json`: 0 ready-to-upload). The 14B release
  is READY_TO_STAGE and waits for explicit operator approval. The 32B has no
  trained artifact; base weights are never republished as trained. `model-publish`
  and `package ship` stay operator-gated CLI actions, never shell buttons.
- **No credentials in code or transit surfaces.** Keys come from environment
  only (`endpoints.py` discipline); the Gemini query-string leak gets fixed,
  not replicated; the health roster reports env-presence booleans, never
  values; receipts and ledgers never contain secrets. `.env` never ships (the
  package secret-scan doctor already enforces this; keep it in the gate).
- **Every shipped surface passes the publish gate.** `harness/publish_lint.py`
  (zero-dep) is the pre-publish check on the shipped-posture flip: it fails on
  secrets and build-machine paths leaking into a product doc, and warns on
  developer-register language ("Status: staged", operator-gate speak) and stale
  claims. It is the scan-and-report mechanism copied from behavior-transform.io's
  pressure_scan and re-based on a product ruleset — the WARDEN red-team
  vocabulary is deliberately NOT imported. Verifier-can-fail: `--selftest` fires
  a falsifier (a dirty doc must raise every category, a clean doc none). The 14B
  HF page and the site both pass it clean today; internal docs (STATE.md, the
  records tree) correctly fail it, which is why they never become product
  surfaces.
- **No capability-uplift claims.** The M7 +10% lift did not reproduce and is
  unearned. The surface markets what is real: receipts, pass parity,
  availability on the operator's schedule, and local cost. The showcase's
  explicit no-uplift note survives the rewrite.
- **No learned authority in the accept path.** Escalation in the companion
  seat is oracle-outcome-driven. A future difficulty heuristic may reorder
  attempts; it may never accept, and its absence must not block acceptance.
- **The verifier can fail, everywhere.** Every new surface ships with its
  tamper falsifier (section 4). A view that cannot show DRIFT is not shipped.
- **Not cross-platform yet.** This is a contract for one Windows + WSL box
  with 32 GB RAM and 24 GB VRAM. The E:\ path constants and the 22 GB WSL RAM
  gate are contracts, not bugs. Config-driven path resolution is future work;
  pretending portability now would be a false claim.
- **Not a training-knob console.** The training view starts, watches, and
  stops the existing supervisor. It never exposes gate bypasses or recipe
  overrides, and hard-stop is a separately confirmed action.
- **No implicit command execution from the browser.** The action surface is a
  short explicit allowlist of the metadata-only receipt emitters plus the two
  gated training controls. The other CLI commands stay CLI.
- **Storage discipline.** Nothing large lands on C:. Runs, checkpoints, caches,
  and weights live on E: per the existing path contract; the file store
  default (`C:/tmp/harness_file_store`) is small JSONL and moves to
  config-driven resolution when the packaging increment touches it.
- **Zero external dependencies.** Stdlib only, in the gateway, the world
  composer, the training wrapper, and the shell (vanilla JS, inline assets,
  no CDN, fully offline). MCP remains the lone optional edge.
- **Operator gates, named:** model publish (HF upload), package ship, training
  start and hard-stop, auto-commit in the agent, anything writing to public
  repos, and this spec's own adoption. This document commits nothing and
  authorizes nothing; it specifies.
