# Example: public lane-count check

User prompt:

```text
Use public Flywheel files to check whether the declared lane count matches the probe-free runtime roster. Keep MCP liveness and model availability separate.
```

Expected behavior:

1. Copy or otherwise pin the public source files being measured.
2. Parse the lane registry from the copied source.
3. Run a probe-free roster only if it is safe and read-only in the current environment.
4. Measure declared count versus observed roster count.
5. Mark per-lane MCP readiness and model availability `UNVERIFIABLE` unless separately probed.
6. Add a passing replay/control and a tampered or missing-evidence control.

Expected result shape:

```text
Checked: copied registry declares N lanes; probe-free roster reports N lanes.
Unknown or unverifiable: per-lane MCP readiness; model endpoint availability.
Does establish: count agreement for the observed files and probe-free function.
Does not establish: live readiness, endpoint reachability, adoption, or external publication.
```
