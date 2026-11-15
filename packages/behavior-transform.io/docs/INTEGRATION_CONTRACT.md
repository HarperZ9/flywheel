# behavior-transform.io Integration Contract

`behavior-transform.io` is a pre/post inference compliance intermediary for
authorized operators. It translates sensitive operational language into
provider-compliant form before inference, and delivers clean responses
afterward. It provides local wrappers, hooks, and shell profiles for moving
text through read, write, exec, fetch, input, and model-boundary channels with
explicit mode and provenance handling.

This repository is the compliance boundary layer. It does not perform offensive
operations or generate harmful content. It translates authorized operational
context into language that aligns with model-provider terms of service.

## Runtime Profiles

| Profile | Purpose | Transform behavior |
|---------|---------|--------------------|
| `ops` | Default operator mode | Calibration enabled |
| `research` | Source-faithful research mode | Passthrough |
| `academic` | Alias for research review | Passthrough |

Switching profile is local state only:

```powershell
python tools/io_state.py --set research
python tools/io_state.py --set ops
```

## Host Surfaces

- CLI JSON envelopes through `tools/behavior_flagship.py`
- Claude Code hooks in `hooks/`
- shell profiles in `profiles/`
- direct safe wrappers in `tools/safe_*.py`
- future MCP adapter surface using the same envelope schema

## Privacy Boundary

Hosts may receive:

- mode and profile names
- wrapper/tool names
- counts
- hashes
- verdicts
- redacted references

Hosts must not require raw prompts, private file contents, secret values,
credentials, hidden environment values, or full model-boundary payloads.

## Receipt Shape

Actions that cross write, exec, fetch, or model-boundary channels should record:

- `action_intent_id`
- `channel`
- `profile`
- `input_hash`
- `output_hash` or `redacted_output_ref`
- `decision_outcome`
- `verification_verdict`
- `evaluated_at`

The receipt must be sufficient to replay the boundary decision without exporting
private source content.
