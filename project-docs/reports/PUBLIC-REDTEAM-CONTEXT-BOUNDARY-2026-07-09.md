# Public Red-Team Context Boundary

Date: 2026-07-09

Status: boundary note and ingestion plan

## Public sources checked

- OpenAI, "Separating signal from noise in coding evaluations": `https://openai.com/index/separating-signal-from-noise-coding-evaluations/`
- Pliny public landing page: `https://pliny.gg/`
- X links supplied by the operator were not readable through the current non-authenticated fetch path.

## Public-source synthesis

OpenAI's coding-evaluation audit reinforces a benchmark rule already added to the flywheel harness: broken tasks, underspecified prompts, overly strict tests, misleading prompts, and low-coverage tests must be separated from model failure. This supports task-quality labels, provenance checks, and benchmark flaw gates before using any result for model promotion.

The Pliny public page positions the ecosystem around public jailbreak research, prompt-injection culture, red-team leaderboards, prompt-leak collections, steganographic prompt tooling, and "abliteration" style refusal-removal tooling. The useful measurement lesson for this project is not to copy jailbreak payloads. The useful lesson is to benchmark adversarial pressure as a first-class environment: prompt-injection resistance, instruction-boundary receipts, proof-backed tool use, and explicit fail-closed behavior.

## Discord boundary

I will not use an authenticated user session to scrape private Discord servers or bulk-extract private member messages.

Permitted ingestion shapes:

- public pages, public documentation, public Discord landing pages, and public repository artifacts
- user-provided exports where the operator has rights to provide them
- server-owner-approved bot ingestion with explicit channel allowlists
- Discord data packages or channel exports processed locally with redaction and receipts

Required ingestion controls:

- source receipt per file/channel/export
- server/channel allowlist
- timestamp and message-id preservation
- author pseudonymization by default
- secret/PII redaction before model-boundary use
- opt-out and deletion support if data is not purely public
- no token capture, credential reuse, or account-session scraping

## Harness implication

Add a future `community_redteam_context` dataset only from public or consented sources. Metrics should measure:

- prompt-injection pattern coverage
- instruction-boundary attack resistance
- proof/witness preservation under adversarial prose
- refusal-removal claim skepticism
- source provenance coverage
- private-data exclusion rate
