# Provider and Model Catalog

> Verified as of 2026-08-03 by parallel first-party-doc research across 11 providers.
> Prices and model ids are volatile: every figure carries a confidence label, and
> honest nulls are kept. This is the data reference for `harness/model_router.py`;
> the routing code is provider-agnostic and does not depend on any single id here.

---

# Unified Model Routing Registry ,  Catalog Seed (normalized 2026-08-03)

Prices are USD per Mtok. All "as of 2026-08-03, verify" caveats from the source blocks carry forward. Confidence labels and honest nulls preserved. This replaces the OpenRouter routing layer; OpenRouter itself is retained below as one optional aggregator upstream, flagged as the incumbent being replaced.

## 1. Provider catalog

| provider | base_url | wire_protocol | anthropic_compat? | auth_header | env_var | quota_429_behavior |
|---|---|---|---|---|---|---|
| anthropic | `https://api.anthropic.com` (native); OpenAI-compat `…/v1/` | anthropic-messages (native `POST /v1/messages`); openai-chat-completions compat layer | native (this is the provider) | `x-api-key: <key>` + `anthropic-version: 2023-06-01`; alt `Authorization: Bearer <oauth token>` | `ANTHROPIC_API_KEY` (Claude Code subscription: `CLAUDE_CODE_OAUTH_TOKEN`) | 429 `rate_limit_error` with `retry-after`; 429 also on acceleration spikes; 529 `overloaded_error` (backoff); 402 `billing_error`; spend cap pauses usage until next month, not a per-request 429. high |
| openai | `https://api.openai.com/v1` | openai-chat-completions (native); native `/responses` API also | none. high | `Authorization: Bearer <key>`; optional `OpenAI-Organization`, `OpenAI-Project` | `OPENAI_API_KEY` | 429 for both cases, split by body `code`: `rate_limit_exceeded` (transient, honor `retry-after`/`retry-after-ms`) vs `insufficient_quota` (billing, retry will not help, route to fallback). Router must read the error body, not just the status. high |
| google-gemini | Dev API `https://generativelanguage.googleapis.com` (`/v1beta`,`/v1`); Vertex `https://{LOCATION}-aiplatform.googleapis.com` | native-other (`generateContent`/`streamGenerateContent`); OpenAI-compat shim at `…/v1beta/openai/` | none documented (moderate, absence-of-evidence) | native `x-goog-api-key: <key>`; OpenAI-compat `Authorization: Bearer <key>`; Vertex `Authorization: Bearer <gcloud-access-token>` (OAuth2/ADC) | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`, precedence when both set) | 429 `RESOURCE_EXHAUSTED` with optional `retryDelay` in body; quota per GCP project (not per key) across RPM/TPM/RPD/IPM; 503 `UNAVAILABLE` is the transient-retry signal, 429 is the hard quota signal. high |
| alibaba-qwen | workspace `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1` (moderate); legacy `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (high); Beijing analogs | native-other (DashScope JSON); openai-chat-completions layer + anthropic-messages layer | yes: `…/apps/anthropic/v1/messages` (moderate); `/v1/messages` only, no `/v1/models` | OpenAI-compat + native: `Authorization: Bearer <key>`; Anthropic-compat: `x-api-key` OR `Authorization: Bearer` | `DASHSCOPE_API_KEY` (Claude Code integration reads `ANTHROPIC_AUTH_TOKEN`) | OpenAI-compat: 429 on rate-limit, 402/quota on balance exhaustion (moderate); native wraps `code`/`request_id` (`Throttling.RateQuota`, `Arrearage`). Specific codes low. |
| deepseek | `https://api.deepseek.com` (also `/v1` compat shim) | openai-chat-completions (primary); native Anthropic surface | yes: `https://api.deepseek.com/anthropic` (high) | `Authorization: Bearer <key>` | `DEEPSEEK_API_KEY` | Limits are account-level concurrency (v4-pro 500, v4-flash 2,500 in-flight), not RPM/TPM; overflow returns 429 (high). 402-on-exhaustion is historical but UNKNOWN/verify (low). |
| mistral | `https://api.mistral.ai/v1`; Codestral FIM `https://codestral.mistral.ai/v1` (moderate) | openai-chat-completions (native OpenAI-shaped, minor extensions) | none. high | `Authorization: Bearer <key>` | `MISTRAL_API_KEY` | 429 Too Many Requests; `X-RateLimit-Remaining` header for pre-emptive backoff; limits per-workspace (all keys share one RPM+TPM); request-rate and token-rate trip independently. moderate |
| xai-grok | `https://api.x.ai/v1` | openai-chat-completions (primary); anthropic-messages surface (moderate) | yes: `https://api.x.ai/v1/messages` (moderate, not live-verified this session) | `Authorization: Bearer <key>` | `XAI_API_KEY` | 429 `rate_limit_exceeded` on RPS/TPM overflow (high); tier set by cumulative spend since 2026-01-01, never downgrades; exponential backoff. |
| openrouter (incumbent, being replaced) | `https://openrouter.ai/api/v1` | openai-chat-completions (superset + routing extensions) | yes: `https://openrouter.ai/api/v1/messages` (high, confirmed live 401) | `Authorization: Bearer <key>` (keys `sk-or-v1-…`); optional `HTTP-Referer`, `X-Title` | `OPENROUTER_API_KEY` | 402 Payment Required = out of credits; 429 = rate limited; 401/403 auth; 502/503 upstream. Mid-stream failures after SSE begins keep the HTTP status and arrive as an SSE event `finish_reason:"error"`, so a failover wrapper must inspect the stream body. high |
| together | `https://api.together.xyz/v1` (also `.ai/v1`, moderate) | openai-chat-completions | none documented (moderate, absence) | `Authorization: Bearer <key>` | `TOGETHER_API_KEY` | 429 on rate-limit/quota with `Retry-After`; 401/403 auth; 400 malformed/over-context; credit exhaustion 402 or 429 (moderate). |
| fireworks | `https://api.fireworks.ai/inference/v1` (Anthropic SDK base `…/inference`) | openai-chat-completions; anthropic-messages | yes: `https://api.fireworks.ai/inference/v1/messages` (high) | `Authorization: Bearer <key>` | `FIREWORKS_API_KEY` (docs also show reusing `OPENAI_API_KEY`) | 429 with `Retry-After`; 401/403; 400; credit 402 or 429 (moderate). `max_tokens` is silently lowered when prompt+max_tokens exceeds context, so no 400 there (moderate). |
| local: ollama | `http://localhost:11434` (native), `…/v1` (OpenAI-compat) | openai-chat-completions; native-other (`/api/chat`,`/api/generate`, NDJSON) | none. high | none local; OpenAI SDK sends placeholder `Authorization: Bearer ollama`; Cloud/Turbo `Authorization: Bearer <key>` | SDK-side `OPENAI_API_KEY=ollama`; Cloud `OLLAMA_API_KEY` | No rate limits or token quotas; concurrent requests queue, not 429. Model not pulled returns an error (`/api/chat` does not auto-pull). high |
| local: vllm | `http://localhost:8000/v1` | openai-chat-completions | none natively; needs external proxy/adapter. high | none by default; with `--api-key`/`VLLM_API_KEY` set, `Authorization: Bearer <key>` | `VLLM_API_KEY` | No rate limits; queues. Unknown model id returns 404 `NotFoundError`; 401 if a key is configured and missing. high |
| local: lm-studio | `http://localhost:1234/v1` (OpenAI-compat); native `/api/v0`,`/api/v1` | openai-chat-completions; native-other (lmstudio REST v0/v1) | yes (moderate on existence, low on exact path; likely `/v1/messages`) | none (access controlled by loopback bind 127.0.0.1) | none | No rate limits; queues. Model not loaded returns 404 (JIT auto-load is an optional setting). high |

## 2. Model catalog

Role assigned from {flagship, workhorse, cheap, reasoning, vision, local}; source blocks that named a compound role (e.g. "flagship/reasoning") are collapsed to the primary and noted below the table. Cache, tiered, and 2-tier price detail preserved inline.

| canonical_model_id | provider | role | context | price_in | price_out | confidence |
|---|---|---|---|---|---|---|
| claude-fable-5 | anthropic | flagship | 1M | $10 | $50 | high |
| claude-opus-5 | anthropic | reasoning | 1M | $5 | $25 | high |
| claude-sonnet-5 | anthropic | workhorse | 1M | $2 intro (→$3 2026-09-01) | $10 intro (→$15 2026-09-01) | high |
| claude-haiku-4-5 | anthropic | cheap | 200k | $1 | $5 | high |
| claude-opus-4-8 | anthropic | reasoning | 1M | $5 | $25 | high |
| gpt-5.6-sol (alias gpt-5.6) | openai | flagship | 1,050,000 (max 922K input) | $5.00 (cached $0.50) | $30.00 | high |
| gpt-5.6-terra | openai | workhorse | 1,050,000 (max 922K input) | $2.00 (cached $0.20) | $12.00 | high |
| gpt-5.6-luna | openai | cheap | 1,050,000 | $0.20 (cached $0.02) | $1.20 | high |
| gpt-5.5 (snapshot gpt-5.5-2026-04-23) | openai | flagship | 1,050,000 | $5.00 (cached $0.50) | $30.00 | high |
| gpt-5 | openai | flagship (legacy) | 400,000 | $1.25 (cached $0.125) | $10.00 | high |
| gemini-3.6-flash | google-gemini | flagship | 1,048,576 / ~65,536 | $1.50 | $7.50 | price: high; ctx: moderate |
| gemini-3.5-flash | google-gemini | reasoning | 1,048,576 / ~65,536 | $1.50 | $9.00 | price: high; ctx: moderate |
| gemini-3.5-flash-lite | google-gemini | cheap | 1,048,576 / ~65,536 (assumed) | $0.30 | $2.50 | price: high; ctx: low |
| gemini-3.1-pro-preview | google-gemini | reasoning | UNKNOWN | UNKNOWN | UNKNOWN | id: high; rest: UNKNOWN |
| gemini-2.5-pro | google-gemini | flagship | 1,048,576 / 65,536 | $1.25 ≤200k / $2.50 >200k | $10.00 ≤200k / $15.00 >200k | price: high; ctx: high |
| gemini-2.5-flash | google-gemini | workhorse | 1,048,576 / 65,536 | $0.30 text·img·video / $1.00 audio | $2.50 | price: high; ctx: high |
| gemini-2.5-flash-lite | google-gemini | cheap | 1,048,576 / 65,536 | $0.10 text·img·video / $0.30 audio | $0.40 | price: high; ctx: high |
| qwen3.7-max | alibaba-qwen | flagship | ~1M (reported, unconfirmed) | UNKNOWN | UNKNOWN | id: moderate; specs: low |
| qwen3.7-plus | alibaba-qwen | workhorse | ~1M (reported) | UNKNOWN | UNKNOWN | id: moderate; specs: low |
| qwen3.6-flash | alibaba-qwen | cheap | ~1M (reported) | UNKNOWN | UNKNOWN | id: moderate; specs: low |
| qwen3-max | alibaba-qwen | flagship | ~256K-262K (prior-known) | UNKNOWN | UNKNOWN | id: moderate; specs: low |
| qwen-max | alibaba-qwen | flagship | UNKNOWN | UNKNOWN | UNKNOWN | id: high; specs: unknown |
| qwen-plus | alibaba-qwen | workhorse | UNKNOWN | UNKNOWN | UNKNOWN | id: high; specs: unknown |
| qwen-turbo / qwen-flash | alibaba-qwen | cheap | UNKNOWN | UNKNOWN | UNKNOWN | id: high; specs: unknown |
| deepseek-v4-pro | deepseek | flagship | 1,000,000 (max out 384K) | $0.435 miss / $0.003625 hit | $0.87 | high (ids/ctx), moderate (price) |
| deepseek-v4-flash | deepseek | workhorse | 1,000,000 (max out 384K) | $0.14 miss / $0.0028 hit | $0.28 | high (ids/ctx), moderate (price) |
| mistral-large-2512 (mistral-large-latest, Large 3) | mistral | flagship | ~256k | $0.50 | $1.50 | price: high; id: high; ctx: moderate |
| mistral-medium-latest (Medium 3.5, v26.04) | mistral | workhorse | ~256k | $1.50 | $7.50 | price: moderate; id: moderate; ctx: moderate |
| mistral-medium-2505 (Medium 3) | mistral | workhorse | ~256k | $0.40 | $2.00 | price: high; id: high; ctx: moderate |
| mistral-small-2603 (mistral-small-latest, Small 4) | mistral | cheap | ~256k | $0.15 | $0.60 | price: high; id: moderate; ctx: moderate |
| codestral-2508 (codestral-latest) | mistral | workhorse | ~256k | $0.30 | $0.90 | price: moderate; id: high; ctx: moderate |
| magistral-medium-2506 | mistral | reasoning | ~128k (older 40k) | $2.00 | $5.00 | price: moderate; id: moderate; ctx: low |
| pixtral-large-2411 (pixtral-large-latest) | mistral | vision | 128k | $2.00 | $6.00 | price: moderate; id: high; ctx: high |
| open-mistral-nemo | mistral | cheap | 128k | $0.02 | $0.03 | price: moderate; id: moderate; ctx: high |
| grok-4.5 | xai-grok | flagship | 500K | $2.00 (2-tier: $4.00 ≥200k) | $6.00 (2-tier: $12.00 ≥200k) | moderate |
| grok-4.3 | xai-grok | workhorse | 1M | $1.25 (2-tier: $2.50) | $2.50 (2-tier: $5.00) | moderate |
| grok-4.20-0309-reasoning | xai-grok | reasoning | 1M | $1.25 (2-tier: $2.50) | $2.50 (2-tier: $5.00) | low-moderate |
| grok-4.20-0309-non-reasoning | xai-grok | workhorse | 1M | $1.25 (2-tier: $2.50) | $2.50 (2-tier: $5.00) | low-moderate |
| grok-4.20-multi-agent-0309 | xai-grok | reasoning | 1M | $1.25 (2-tier: $2.50) | $2.50 (2-tier: $5.00) | low-moderate |
| grok-build-0.1 | xai-grok | cheap | 256K | $1.00 (2-tier: $2.00) | $2.00 (2-tier: $4.00) | low-moderate |
| anthropic/claude-opus-4.6 | openrouter | flagship | 1,000,000 | $5.00 | $25.00 | high |
| anthropic/claude-sonnet-4.6 | openrouter | workhorse | 1,000,000 | $3.00 | $15.00 | high |
| openai/gpt-5.2-codex | openrouter | reasoning | 400,000 | $1.75 | $14.00 | high |
| openai/gpt-5.1 | openrouter | flagship | 400,000 | $1.25 | $10.00 | high |
| x-ai/grok-4.5 | openrouter | reasoning | 500,000 | $2.00 | $6.00 | high |
| deepseek/deepseek-v3.2 | openrouter | cheap | 163,840 | $0.27 | $0.40 | high |
| google/gemini-2.5-flash-lite | openrouter | cheap | 1,048,576 | $0.10 | $0.40 | high |
| meta-llama/llama-4-scout | openrouter | cheap | 1,310,720 | $0.10 | $0.30 | high |
| meta-llama/Llama-3.3-70B-Instruct-Turbo | together | workhorse | 131,072 | ~0.88 (pricing page showed 1.04) | ~0.88-1.04 | id: high / price: low |
| deepseek-ai/DeepSeek-V3 | together | flagship | ~131k | ~1.25 | ~1.25 | id: moderate / price: low |
| deepseek-ai/DeepSeek-R1 | together | reasoning | ~163k | ~3.00 | ~7.00 | id: moderate / price: low |
| openai/gpt-oss-120b | together | workhorse | ~128k | 0.15 | 0.60 | id: moderate / price: moderate |
| openai/gpt-oss-20b | together | cheap | ~128k | 0.05 | 0.20 | id: moderate / price: moderate |
| accounts/fireworks/models/llama-v3p1-405b-instruct | fireworks | flagship | 131,072 | ~3.00 | ~3.00 | id: high / price: low |
| accounts/fireworks/models/llama-v3p3-70b-instruct | fireworks | workhorse | 131,072 | ~0.90 | ~0.90 | id: high / price: low |
| accounts/fireworks/models/deepseek-r1 | fireworks | reasoning | ~160k | ~3.00 | ~8.00 | id: moderate / price: low |
| llama3.1:8b | local: ollama | local | 128K native / 4K served default | 0 | 0 | high (convention), moderate (served ctx) |
| qwen2.5:7b / qwen2.5-coder:7b | local: ollama | local | 128K native | 0 | 0 | high |
| gemma3:12b | local: ollama | local | 128K native | 0 | 0 | moderate |
| deepseek-r1:7b / :14b | local: ollama | local | 128K / 64K native | 0 | 0 | moderate |
| meta-llama/Meta-Llama-3-8B-Instruct | local: vllm | local | set by `--max-model-len` | 0 | 0 | high (convention) |
| qwen2.5-7b-instruct | local: lm-studio | local | set at load time | 0 | 0 | high (convention) |

Role collapses (source primary role kept, secondary noted): claude-opus-5 and claude-opus-4-8 are "flagship/reasoning" and "workhorse/reasoning"; gemini-3.6-flash is "flagship/workhorse"; gemini-2.5-flash is "workhorse/vision" (multimodal); deepseek-v4-pro is "flagship/reasoning"; deepseek-v4-flash is "workhorse/cheap/reasoning"; mistral-medium-latest is "flagship/coding-agentic"; codestral-2508 is "coding" (mapped to workhorse); mistral-small-2603 is "cheap/workhorse" hybrid reasoning+vision; grok-4.20-multi-agent is "reasoning/agentic"; grok-build-0.1 is "cheap/coding"; openai/gpt-5.2-codex and anthropic/claude-opus-4.6 are "flagship/reasoning"; google/gemini-2.5-flash-lite and meta-llama/llama-4-scout are "cheap/vision"; openai/gpt-oss-120b is "workhorse/reasoning"; the Ollama locals carry native secondary roles (qwen2.5 cheap, gemma3 vision, deepseek-r1 reasoning).

### Legacy / restricted / retired (callable or catalog-adjacent, not default routing targets)

- Anthropic legacy, still callable, $5/$25: claude-opus-4-7, claude-opus-4-6, claude-opus-4-5. Sonnet legacy $3/$15: claude-sonnet-4-6, claude-sonnet-4-5. Deprecated claude-opus-4-1-20250805 $15/$75, retiring 2026-08-05. Restricted: claude-mythos-5 shares Fable 5 specs and $10/$50 pricing but is invitation-only (Project Glasswing), not self-serve. (high)
- OpenRouter alternates confirmed live: openai/gpt-5.2-chat 128K $1.75/$14; google/gemini-3-pro-image 131K $2/$12; meta-llama/llama-4-maverick 1.05M $0.20/$0.80; x-ai/grok-4.3 1M $1.25/$2.50. (high)
- Gemini embeddings: gemini-embedding-2 text $0.20/Mtok (not a chat model). (high)
- DeepSeek retired 2026-07-24 15:59 UTC, now 404: deepseek-chat, deepseek-reasoner. Thinking is now a parameter (`thinking:{"type":"enabled"}`), not a model id. (high)

## 3. Routing notes

**One OpenAI-chat adapter serves the majority.** These speak openai-chat-completions as their native or primary wire, so a single OpenAI-shaped client (base_url + key swap) reaches all of them: openai, deepseek, mistral, xai-grok, openrouter, together, fireworks, and all three local engines (ollama `/v1`, vllm `/v1`, lm-studio `/v1`). The same adapter also reaches anthropic, google-gemini, and alibaba-qwen through their OpenAI-compat shims, with caveats: Anthropic's compat layer is test/eval-grade only (no prompt caching; `strict`/`response_format`/`seed`/`reasoning_effort` ignored; `n` must be 1), and the Gemini and Qwen shims are secondary surfaces over a native-other core.

**Native anthropic-messages upstream (one provider).** anthropic is the canonical anthropic-messages provider via `POST /v1/messages`; an Anthropic-SDK client points here directly.

**Anthropic-compatible endpoints (drop-in for an Anthropic-SDK client, no translation adapter).** deepseek (`/anthropic`, high), openrouter (`/api/v1/messages`, high, live-confirmed), fireworks (`/inference/v1/messages`, high), xai-grok (`/v1/messages`, moderate), alibaba-qwen (`…/apps/anthropic/v1/messages`, moderate, no `/v1/models` so model discovery must be static), and lm-studio locally (moderate existence, low on exact path). This means deepseek and fireworks in particular can slot into either an OpenAI-style or an Anthropic-style failover lane without any body translation.

**No Anthropic surface (route via OpenAI wire or skip for Anthropic-SDK lanes).** openai (high), google-gemini (moderate, absence), mistral (high), together (moderate, absence), ollama (high), vllm (high natively, needs an external proxy for `/v1/messages`).

**Providers that benefit from a native adapter (native-other wire).** google-gemini is the main one: its native `generateContent`/`streamGenerateContent` is native-other, and full feature coverage lives there rather than in the OpenAI shim; the shim is the low-effort path if you can accept its limits. alibaba-qwen native DashScope JSON is the full-feature protocol, but its OpenAI-compat and Anthropic-compat layers cover most routing needs, so a native adapter is optional. ollama native `/api/chat` (NDJSON) and lm-studio native REST are also optional; target `/v1` for OpenAI SSE unless you need engine-specific features.

**Failover mechanics worth encoding in the registry.** Read the error body, not just the status: OpenAI splits transient `rate_limit_exceeded` from hard `insufficient_quota` both under 429; Gemini's 503 is retryable while 429 is hard quota. OpenRouter (and any Anthropic/OpenAI streaming lane) can fail mid-stream after SSE starts with `finish_reason:"error"` at an unchanged HTTP status, so a wrapper must inspect the stream. Long-context cost cliffs exist on openai (>272K tokens at 2x in / 1.5x out), xai-grok (~200K threshold roughly doubles the whole request), and gemini-2.5-pro (>200K tier). DeepSeek prices are time-of-day dependent (2x during Beijing peak windows, moderate). Model-id namespacing differs and is not interchangeable: OpenRouter `org/model`, Together HuggingFace-style `org/Model-Name`, Fireworks `accounts/fireworks/models/<slug>`, Ollama `name:tag`, so a router must translate ids per provider. For local engines the failover signal is model-not-available (404 on vllm/lm-studio, pull-required error on ollama), not quota.

## 4. Honest nulls (UNKNOWN or unverified, listed plainly)

- **openai:** platform reference page returns 403 to fetch; the auth scheme is stated high-confidence but was not re-verified against the JS-rendered reference this pass. The 5.6-family >272K long-context surcharge is assumed from 5.5, verify (moderate). Batch/Flex ~50% and Priority ~2.5x lanes: moderate. UNKNOWN this pass: o-series / GPT-4.1 / GPT-4o pricing; exact per-tier RPM/TPM numbers; the first-party subscription-OAuth token/endpoint contract.
- **anthropic:** using the Claude Code subscription OAuth token as a raw Messages-API adapter is unofficial (moderate). All model prices/ids carry "verify".
- **google-gemini:** anthropic-compat endpoint absence is moderate (absence-of-evidence). 3.x context windows corroborated only by secondary sources (moderate/low). gemini-3.5-flash-lite ctx assumed (low). gemini-3.1-pro-preview context, price, and full role are UNKNOWN (not on the pricing page; preview ids can be retired on short notice). Tier auto-upgrade thresholds moderate; error-status mapping moderate.
- **alibaba-qwen:** workspace base_url host moderate. Anthropic-compat endpoint moderate, and it exposes no `/v1/models`. Consumer OAuth is a chat-UI session, not a documented API auth path (moderate). ALL Qwen model prices are UNKNOWN (official pricing page 404'd twice). The assumed qwen3.8-max family could not be confirmed on any official page (search-summary/SEO only); treat qwen3.8-* as UNKNOWN. The assumed "$2/$6" flagship price is UNCONFIRMED (third-party blogs disagree: $2.50/$7.50 vs $1.20/$3.00 vs $0.78/$3.90). Context windows are reported/unconfirmed (low). Free-tier grants unverified (low). Specific native error codes low.
- **deepseek:** V4 prices moderate. 402-on-exhaustion UNKNOWN/verify (low). Peak-hours 2x surcharge moderate, with one doc flagging rollout as "pending". Consumer OAuth is a web session, not an API path (moderate).
- **mistral:** official docs render client-side and were not directly parseable; the table is aggregator-corroborated. mistral-medium-latest price is ambiguous between Medium 3 ($0.40/$2.00) and Medium 3.5 ($1.50/$7.50) depending on when the alias flipped, verify. Several id date-suffixes moderate. codestral.mistral.ai endpoint moderate. Rate-limit tiers and 429 headers moderate. auth_subscription_oauth is no (moderate). UNKNOWN ids and prices: Ministral 3 family (`ministral-3-14b/8b/3b-2512`), Devstral 2 (`devstral-2512`), Magistral Small 1.2, Pixtral 12B, and the Voxtral / Mistral OCR / Mistral Moderation specialists.
- **xai-grok:** the anthropic `/v1/messages` endpoint rests on secondary sources this session (moderate). Model prices moderate to low-moderate. The served alias for the grok-4.20 variants (bare `grok-4.20` vs the `-0309` snapshot) is UNKNOWN, verify via `GET /v1/models`. Cached-input pricing low. Legacy grok-4 (~$3/$15) and grok-3 are UNKNOWN/legacy. Built-in tool prices (Web/X Search, Code Execution, File Attachments, Collections) low-moderate. Exact rate-limit tier numbers moderate.
- **openrouter:** prices are the canonical/default listing only; because OpenRouter is a pricing passthrough, the actual per-request price varies by which sub-provider routing selects.
- **together / fireworks:** Together `.ai/v1` host working is moderate. Together anthropic-compat absence is moderate. All specific model ids beyond convention, context windows, and prices are moderate-to-low and volatile; enumerate live via `GET /v1/models` per provider. UNKNOWN until confirmed: newer families surfaced in page reads but not verified (`Qwen/Qwen3.6-Plus`, `deepseek-ai/DeepSeek-V4-Pro`, GLM-5.x, plus Llama 4 Maverick/Scout, Qwen3, Kimi). Credit-exhaustion code (402 vs 429) moderate. Fireworks size-tiered pricing and `max_tokens` silent-lowering moderate. auth_subscription_oauth is no for both (moderate).
- **local (ollama / vllm / lm-studio):** Ollama served-ctx default of 4096 is moderate and is a load-time setting, not a catalog value. LM Studio Anthropic-compat existence moderate, exact path low; native `/api/v1` path/version moderate. Cold-start latency after idle unload (`OLLAMA_KEEP_ALIVE`) moderate. Ollama Cloud/Turbo sign-in path moderate. There is no fixed model catalog for local serving: the id is whatever was pulled or loaded, so all local ids above are representative conventions, not a fixed list.
