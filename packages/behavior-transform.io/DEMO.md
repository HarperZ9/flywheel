# behavior-transform.io Demonstration

The behavior-transform.io demo shows a local IO boundary event becoming a
mode-aware receipt. It is value-free and does not export raw private payloads.

## Run

```powershell
behavior-transform status --json
behavior-transform doctor --json
behavior-transform demo --json
python -B tools\behavior_flagship.py doctor --json
```

## What To Inspect

- mode/profile setting
- channel identity
- receipt verdict
- redacted reference and count metadata
