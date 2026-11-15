# behavior-transform.io Usage

`behavior-transform.io` exposes Project Telos IO boundary checks through a
small flagship action surface and local wrapper utilities.

## Installable CLI

From a local checkout:

```powershell
python -m pip install -e .
behavior-transform status --json
behavior-transform doctor --json
behavior-transform demo --json
```

Compatibility alias:

```powershell
behavior-transform-io doctor --json
```

Direct script invocation remains available:

```powershell
python tools\behavior_flagship.py status --json
python tools\behavior_flagship.py doctor --json
python tools\behavior_flagship.py demo --json
```

## IO Modes

```powershell
python tools\io_state.py --set research
python tools\io_state.py --set ops
```

- `ops`: calibration stack active
- `research`: source-faithful passthrough
- `academic`: research alias

## Verification

```powershell
python -B -m unittest tests.test_behavior_flagship -v
python -B tools\behavior_flagship.py doctor --json
```

The doctor checks required front-door files, hook/profile presence,
installable console scripts, and the redacted IO privacy boundary.

## Boundary

Hosts receive mode, profile, tool names, counts, hashes, verdicts, and redacted
references. Raw prompt bodies, private file contents, and secret values stay
inside local IO adapters.
