# Flywheel 1.3.1

The desktop Usage screen now charts a local model's generation and
prompt-processing speed while it runs. The chart reads counters from a llama.cpp
or vLLM server on your own machine and sends nothing anywhere. This release also
carries the first build of native provider sessions for Codex and Claude, and it
relicenses the Claude Code mod to match Flywheel.

## Try it

```
pip install -U flywheel-verify
flywheel monitor owner        # prints your config and the installed rule-pack digest
```

On Windows, install `Flywheel-Setup-1.3.1-x64.exe` from this release. Open
Usage, pick a llama.cpp or vLLM endpoint in Chat, and the Model activity panel
starts reading its counters.

## Watch a local model work

- The Model activity panel plots tokens per second for generation and for
  prompt processing over the last 60 readings, one row per model.
- It reads llama.cpp `/slots` and vLLM `/metrics` once a second. It never
  starts a model or sends a prompt.
- It only connects to a loopback address such as `127.0.0.1`. It refuses
  redirects, stops after 0.6 seconds and reads at most 256 KiB per reading.
- The route behind it, `/api/usage/live`, needs the gateway token.
- Model file paths and unusual labels show as a short stable code, so a chart
  never displays a local path.
- Pause stops the readings. Leaving the screen or putting the app in the
  background stops them too. A failed reading marks the chart stale and leaves
  a gap.
- A counter the runtime does not report stays "Not reported". Power draw is not
  measured yet.
- Screen readers hear each chart's latest and peak rate, and the status line
  announces a pause, a stale reading and a recovery.

Rates are counter changes over a measured interval. They say how fast the
runtime worked. They say nothing about answer quality.

## Native provider sessions (preview)

- The gateway can run persistent Codex and Claude sessions that you can resume.
  Each session runs inside the existing operation, grant and trace path, and
  any approval it asks for comes back to you.
- The desktop Chat header has a `native` mode for these sessions. A session
  needs a bound provider config before it runs.
- New gateway flags configure a managed Codex runtime:
  `--managed-codex-executable`, `--managed-codex-executable-sha256`,
  `--managed-codex-model`, `--managed-codex-version` and
  `--managed-codex-policy-root`.
- `codex-cli` now asks you to pick a model and returns
  `MODEL_SELECTION_REQUIRED` (HTTP 422) when none is set. The desktop model
  picker shows "Explicit model selection required" for such an endpoint.
- `--strict-bind` makes the gateway refuse to start when it cannot open every
  host it was asked to bind. The mobile launcher's tailnet-only mode passes it.
  The launcher reads `tailscale status` to find your tailnet address and never
  logs in or changes Tailscale settings.
- Managed Codex keeps its baseline policy records under
  `state/codex-managed-policy`. The trace inventory now lists this store, so
  an inventory of your trace data names it.

No speed or accuracy uplift is claimed for native sessions. The Android handoff
acceptance tests in this release need a phone or an emulator, and they were not
run for this release.

## Claude Code mod license

The mod under `integrations/claude-code-mod/` now uses `FSL-1.1-MIT`, the same
license as the rest of Flywheel, and its folder carries the license text. Two
audit test fixtures have neutral names: `forged-consent-sample` and
`permissive-policy-sample`.

## Check this release

- PyPI: `flywheel-verify==1.3.1`
- Windows installer: `Flywheel-Setup-1.3.1-x64.exe`, with its hash in
  `SHA256SUMS.txt`
- The monitor rule pack is unchanged from 1.3.0, so a pinned
  `expected_rules_digest` keeps working. `flywheel monitor owner` prints this
  digest as `installed_rules_digest`:

```
7a3eb877853df959503d3b6925c042bc13fe5d9726381fabf7bd6e8b3861bd52
```
