# behavior-transform.io

Consolidated pre/post inference governance surface.

## Purpose

Single native surface for the full inference boundary stack:
- 14-category content detection with 4-tier thresholds (`tools/categories.py`)
- 5-layer semantic modulation: lexical substitution, compound reframing, technique mapping, density restructuring, authorization framing (`tools/semantic_modulator.py`)
- ATT&CK-phase-aware cyber modulation with 12 assessment phases (`tools/cyber_modulator.py`)
- 150+ vocabulary substitution rules with double-substitution guard (`tools/vocabulary_substitutions.py`)
- Pre-inference pipeline: pressure scan, policy gate, friction score, vocabulary modulation (`tools/pipeline.py`)
- Token optimization: deterministic stdlib-only prompt compression (`tools/token_optimizer.py`)
- Truth profile injection with raw/paragraph/list render modes (`tools/truth_profile.py`)
- Preflight verification: capsule, manifest, seal, receipt system (`tools/preflight/`)
- Full-stack apparatus: protocol proxy, model gateway, conditioning, target inoculation (`tools/apparatus/`)
- Witness subsystem: coherence membrane, temporal perception, drift monitoring (`tools/apparatus/witness/`)
- Vocabulary calibration (T1/T2 term substitution, `tools/vocabulary_map.py`)
- Structural intent reframing (`tools/semantic_intent_reframer.py`)
- Mode-aware channel routing: ops vs. research (`tools/io_state.py`)
- Safe wrappers for all IO channels: file, exec, fetch, stdin, MCP (`tools/safe_*.py`)
- Hook infrastructure for Claude Code (`hooks/`)
- Full-stack validation CLI: run text through all layers and report (`tools/validate.py`, entry point `bt-validate`)
- 22-check subsystem health verification (`tools/subsystem_doctor.py`, entry point `bt-doctor`)

## Entry Points

| Command | Module | Purpose |
|---------|--------|---------|
| `bt` | `tools.bt_cli:main` | Unified CLI dispatcher (validate, doctor, transform, scan, modulate, calibrate, mode, status) |
| `bt validate <text>` | | Run text through all layers and report |
| `bt transform <text>` | | Full-stack semantic transform (normalization + categories + vocab + modulation + calibration) |
| `bt scan <text>` | | Pre-inference pipeline scan (pressure, policy, friction, gate signal) |
| `bt modulate <text>` | | Apply 5-layer semantic modulation |
| `bt adaptive <text>` | | Adaptive multi-pass modulation with obfuscation detection and density escalation |
| `bt calibrate <text>` | | Apply multilingual prose vocabulary calibration |
| `bt normalize <text>` | | Detect and remove obfuscation (leetspeak, homoglyphs, zero-width, spacing) |
| `bt density <text>` | | Analyze semantic density and escalation level |
| `bt discover [paths]` | | Find uncalibrated vocabulary in the codebase |
| `bt doctor` | | 22-check subsystem health verification |
| `bt mode` | | Show current IO mode and profile |
| `bt status` | | Full surface status |
| `bt-validate` | `tools.validate:main` | Standalone validate entry point |
| `bt-doctor` | `tools.subsystem_doctor:main` | Standalone doctor entry point |
| `bt-adaptive` | `tools.adaptive_modulator:main` | Standalone adaptive modulation entry point |

All subcommands accept `--json` for structured output.

## Origin

Consolidation of four sources into one surface:
- `opsec/sofer` classifier_modifier_layer (14-category semantic modulation)
- `ai-safety-prefire` (pre-inference pipeline, token optimizer, truth profile)
- `warden-prefire-primitive` (preflight verification subsystem)
- `ai-safety-guardrail-manager` (apparatus, gateway, conditioning, witness)

The remote repositories are archived. This surface is the canonical location.

## Modes

| Mode | Profile | Behavior |
|------|---------|----------|
| `ops` | standard | Full calibration stack active |
| `research` | native | True passthrough, no substitution |
| `academic` | native | Alias for research |

Switch mode:
```
python tools/io_state.py --set research
python tools/io_state.py --set ops
```

## Structure

```
tools/                   Core modules (flat, all imports resolve locally)
  categories.py          14-category detection engine (HarmCategory enum, 4 tiers)
  semantic_modulator.py  5-layer general semantic modulation
  cyber_modulator.py     ATT&CK-phase-aware cyber modulation
  vocabulary_substitutions.py  150+ term substitution rules
  response_demodulator.py      Return-leg reversal
  content_generator.py         Red-team probe/variant generation
  surface_heatmap.py           Surface temperature tracking
  modulation_context.py        Request-scoped context vars
  modulation_orchestrator.py   Wires all subsystems together
  pipeline.py            Pre-inference pipeline (4-pass)
  vocab_backend.py       Pluggable vocabulary backend resolution
  token_optimizer.py     Deterministic prompt compression
  truth_profile.py       Truth profile loader + injector
  io_state.py            IO mode state
  io_mode.py             Mode switching
  vocabulary_map.py      Identifier calibration map
  prose_vocabulary_map.py  Multilingual prose calibration
  semantic_intent_reframer.py  Structural intent reframing
  adaptive_modulator.py  Adaptive multi-pass modulation (obfuscation detection, density escalation, convergence)
  operator_classifier.py       8-category native classifier
  container_ecosystem.py       Orchestrator
  pressure_scan.py       Pressure scan
  safe_*.py              Safe IO wrappers
  classifier/            Native classifier package
  preflight/             Preflight verification subsystem (14 modules)
    capsule.py           Sovereignty capsule loader
    manifest.py          Surface manifest validator
    seals.py             Cryptographic integrity seals
    receipts.py          Timestamped receipts with secret screening
    launcher.py          High-level launch orchestrator
    audit.py             12-gate audit
    doctor.py            Health check
    ...
  apparatus/             Full-stack inference governance (15 modules)
    orchestrator.py      Apparatus class (status/run/verify)
    boot.py              Boot sequence (env/proxy/targets)
    substrate.py         Canonical truth record
    protocol.py          HTTP loopback proxy (port 7319)
    gateway.py           Universal model gateway (anthropic/openai/gemini/ollama)
    conditioning.py      Inference conditioning (prefill/few-shot/parameters)
    state_projection.py  Carrier-state projection
    inoculation.py       Existence delivery engine
    target.py            Target descriptor
    universal.py         Target-agnostic governance
    witness/             Coherence + drift monitoring
      membrane.py        Anchor/verify/refuse/corroborate/audit
      organs.py          Watch/observe temporal perception
      monitor.py         Drift + marker census
hooks/                   Claude Code hooks
  prefire-truth-inject.py     Truth profile injection (SessionStart)
  safe-premodel-gate.py       Classification + token optimization gate
  session-start-calibrate.py  Session start maintenance
  block-secrets.py            Secret leak prevention
  safe-*-redirect.py          IO redirect hooks
  post-tool-calibrate.py      Post-tool calibration
profiles/                Shell mode-switch scripts
tests/                   Test suite
```

## Tools path

Set `BEHAVIOR_TRANSFORM_TOOLS` env var to override the tools directory
resolution in hooks. Defaults to `../tools/` relative to the hook file.

## Key environment variables

| Variable | Purpose |
|----------|---------|
| `BEHAVIOR_TRANSFORM_TOOLS` | Override tools directory path |
| `PREFIRE_TRUTH_PROFILE` | Path to truth profile JSON |
| `PREFIRE_CONDITIONING` | Path to conditioning config JSON |
| `PREFIRE_TOKEN_OPTIMIZE` | Enable/disable token optimization (default: 1) |
| `PREFIRE_VOCAB_MAP` | Path to vocabulary map module |
| `WARDEN_IO_CHANNEL` | IO mode override |

## Never

- Commit `.env`
- Commit `.warden/io-mode.json` (workstation-local state)
- Add offensive tooling to this repo
- Import from `warden_shell`, `warden_per_turn_dispatcher`, or any WARDEN module
- Hardcode `AGENTS/warden_shell` paths
- Call `context_modulate.py`, `batch_modulate_memory.py`, or `workstation_calibrate.py`
- Import from `ai_safety_prefire`, `ai_safety_guardrail_manager`, or `sofer` (those are archived; everything is local now)
