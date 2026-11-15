<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/behavior-transform.io/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/behavior-transform.io/main/docs/art/hero-light.svg" alt="behavior-transform.io: One compliance boundary between authorized operators and AI providers. Bundles of fine lines carry the work through 5 stations, categorize, substitute, frame, transform and gate, along a sweeping path into a bright core." width="100%">
</picture>

# behavior-transform.io

One compliance boundary between authorized operators and AI providers.

```
python -m pip install -e .
```

[![CI](https://github.com/HarperZ9/behavior-transform.io/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/behavior-transform.io/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-Proprietary-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/behavior-transform.io/blob/main/LICENSE)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-e6e1d6?style=flat-square&labelColor=1a1712)

<img src="docs/art/behavior-transform-io-header.svg" alt="behavior-transform.io, a compliance boundary between an authorized operator and a model provider. One compliance boundary for every provider.">

`behavior-transform.io` is a pre/post inference compliance intermediary. It sits
between an authorized operator and an AI model provider, transforming sensitive
operational context into language that falls within the provider's terms of
service before inference, and stripping formatting artifacts from the response
afterward.

<img src="docs/art/layers-table.svg" alt="A table of fourteen rows: what the boundary declares, how many of it there are, and where each number is read from. Category detection sorts text across fourteen content categories. The transform stack applies seven passes in order. Vocabulary substitution loads 198 rules across four tiers from a backend of 559 terms. Semantic modulation carries fourteen category frames, cyber modulation twelve assessment phases and 71 technique mappings, and prose calibration 305 pairs across fourteen languages. Seven authority gates sit over five deployment surfaces, and refusal recovery escalates through five levels. Nine hundred and six test functions across seventy-seven files pin the behavior. No before-and-after refusal rate is recorded anywhere in the tree, so nothing here measures how much a provider's response to a request actually changes.">

## Who this is for

Law enforcement, government, military, and authorized security operations teams
that use AI models as part of their operational workflows. These entities conduct
work that is legal, internally authorized, and conducted under formal rules of
engagement, but that uses terminology and describes scenarios a general-purpose
model provider will flag or refuse under its default content policy.

Enterprise agreements with providers exist for this purpose. Anthropic, OpenAI,
and Google each offer government and enterprise tiers with scoped policy
adjustments. Those agreements work, but they create a separate relationship per
provider, each with its own onboarding, compliance surface, and failure modes.
An organization using three providers maintains three policy boundaries, three
sets of credentials, and three integration surfaces. When a provider tightens
its content policy, every downstream consumer of that agreement absorbs the
friction individually.

behavior-transform.io is a single compliance boundary. One integration point
handles the vocabulary translation, authorization framing, and policy-gate
logic for every provider behind it. One boundary means one failure point to
diagnose, one configuration to audit, and one surface to maintain. It reduces
the N-to-N relationship between authorized entities and model providers to a
hub that both sides connect to.

## What it is not

behavior-transform.io is not an offensive tool and does not perform offensive
operations. It does not generate attacks, produce harmful content, or provide
capabilities the operator does not already have authorization for.

It is not a jailbreak. A jailbreak attempts to make a model act against its
safety training for any user. This tool translates authorized operational
language into a register that aligns with provider terms of service, for
operators whose authorization is established before the tool runs. The
distinction is the authorization chain: if the operator does not hold a valid
grant, the tool's gate system blocks the request.

## How it works

The tool runs eight layers on every request before it reaches a model:

<img src="docs/art/request-to-model.svg" alt="Eight stages carrying an operator request to a model: input, obfuscation, categories, vocabulary, semantic, cyber, prose, framed request. The raw text is first checked for obfuscation, so leetspeak and homoglyph spacing are normalized before anything reads it. Category detection sorts the text across fourteen content categories. Vocabulary substitution applies a table of rules that swap operational terminology for a consulting register. Semantic modulation runs a five-layer pass with one framing template per category. Cyber modulation maps terminology for twelve assessment phases onto their published equivalents. Prose calibration normalizes register across the whole text against a large multilingual table. The authorization frame is built during the semantic and cyber passes and prepended once at the very top, so it rides on top of the request rather than being woven through it. Research mode is a separate path: a caller who wants no rewrite sends the source text through unchanged, which is why the native path returns to the input. Three outcomes: a request rewritten, framed and sent; a request the caller chose to send natively; and a request the authority gate refused before any layer ran.">

1. **Category detection** classifies the input across 14 content categories.
2. **Vocabulary substitution** replaces operational terminology with
   consulting-register equivalents (150+ rules).
3. **Semantic modulation** applies five layers of contextual rewriting.
4. **Cyber modulation** maps ATT&CK-phase terminology to assessment language.
5. **Prose calibration** normalizes register across the full text.
6. **Compound reframing** handles multi-clause constructions.
7. **Authorization framing** adds context establishing the operator's
   authorization basis.
8. **Token optimization** compresses the result for efficient inference.

On the return leg, the response passes through an output enforcer that strips
formatting artifacts and preamble boilerplate, so the operator receives a clean
operational response.

The **pipeline scan** (`bt scan`) evaluates a request without transforming it,
reporting pressure (estimated refusal probability), policy gate decision, and
friction score. This lets an operator preview whether a request needs
transformation before sending it.

The **authority system** derives authorization from the deployment environment:
machine fingerprint, capsule integrity, seal validity, and activation state. No
external auth server or token exchange is needed. If the grant is invalid, the
tool blocks the request.

<img src="docs/art/grant-to-verdict.svg" alt="Eight stages taking a deployment to a verdict: environment, capsule, seal, activation, grant, surface, policy, verdict. The environment yields a machine fingerprint. A capsule is loaded and its integrity checked, a seal is verified, and an activation state is read. From those four signals a grant is derived with a one-hour lifetime, and if any signal is missing the derivation returns no grant rather than a partial one. The grant is matched to one of five deployment surfaces, each of which lists the entitlements it is allowed to ask for. The policy layer then evaluates four rules through four evaluators covering compound entitlements, rate limits, cooldowns and session requirements. A gate returns its verdict. Seven named gates sit on the entitlements the surfaces expose. Three outcomes: a call authorized because the grant covers the gate, a call held back by a rate limit or cooldown even though the grant is valid, and a call denied because there is no grant or the surface never carried that entitlement.">

## Usage

```bash
python -m pip install -e .
bt --help
bt status --json
bt doctor --json
```

For full commands, see [USAGE.md](USAGE.md) and
[GETTING-STARTED.md](GETTING-STARTED.md).

## For developers

Run the flagship tests and doctor before changing any subsystem:

```bash
python -B -m pytest tests/test_behavior_flagship.py tests/test_behavior_delivery_contract.py -q
python -B tools/behavior_flagship.py doctor --json
```

Delivery-surface changes should also pass:

```bash
python -m public_surface_sweeper . --workspace --json
```

## Modes

| Mode | Profile | Behavior |
|------|---------|----------|
| `ops` | standard | Full calibration stack active |
| `research` | native | Source-faithful passthrough, no substitution |
| `academic` | native | Alias for research |

Switch mode:

```bash
python tools/io_state.py --set research
python tools/io_state.py --set ops
```

## Structure

```text
tools/      Core modules and CLI wrappers
hooks/      Claude Code hook adapters
profiles/   Shell integration helpers
tests/      Pytest and unittest coverage
docs/       Specs, plans, and integration contracts
```

## Verification

```bash
python -m pytest -q
bt doctor --json
```

See [docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md) for the IO
boundary contract. See [AGENTS.md](AGENTS.md) for local agent instructions and
[USAGE.md](USAGE.md) for operator/developer commands.
