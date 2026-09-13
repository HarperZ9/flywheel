# METR interoperability boundary

Researchers should be able to retain evidence from an external evaluation
without moving their task implementation, scoring authority or sandbox into
Flywheel. The current implemented entry point is
[`flywheel import-inspect`](INSPECT-EVIDENCE.md). A METR task executed through
Inspect can use that log format, subject to the documented import limits.
This does not establish METR Task Standard execution conformance.

## Reference execution route

The first-party [METR Inspect bridge](https://github.com/METR/inspect-metr-task-bridge)
constructs an Inspect task from a METR task image. It supplies the dataset,
setup, solver, scorer and cleanup. The bridge's example uses:

```text
inspect eval mtb/bridge -T image_tag=count_odds-0.0.1 --sample-id hard
```

That command is an upstream reference, not a command executed by Flywheel's
importer. It requires the separate bridge runtime and a working sandbox.
Inspecting a log does not demonstrate that image setup, permissions, scoring or
cleanup were correct.

The initial integration target is the small `count_odds` example. Its known
answer allows a wrong-answer control without purchasing model inference or
running a large research benchmark. An actual bridge run and immutable task
image digest are still required before describing this route as tested.

## Reviewed source identities

The reference review on 2026-09-13 used these upstream revisions:

| Component | Revision | Declared version |
| --- | --- | --- |
| [Task Standard](https://github.com/METR/task-standard/tree/03236e9a1a0d3c9f9d63f6c9e60a9278a59d22ff) | `03236e9a1a0d3c9f9d63f6c9e60a9278a59d22ff` | `0.5.0` |
| [Inspect bridge](https://github.com/METR/inspect-metr-task-bridge/tree/20a430cc59283c8b463e526e77f8d040509457ec) | `20a430cc59283c8b463e526e77f8d040509457ec` | `mtb 0.5.24` |
| [Task Standard Python package](https://github.com/METR/vivaria/tree/20a6c290c3c11f701af95a559d9d0c64dd6105d4/python-package) | `20a6c290c3c11f701af95a559d9d0c64dd6105d4` | `0.1.2` |

The reviewed bridge declares Python `>=3.13,<4`. Its source dependencies also
need resolved revisions; a package version alone does not freeze that runtime.
The bridge lists unsupported auxiliary VMs as a limitation. Tasks requiring
unsupported resources must fail visibly rather than run in a reduced environment.

No upstream task or bridge source is vendored here. Review the applicable
licenses before redistributing implementations or images. Repository metadata
alone is insufficient to resolve a missing or conflicting license declaration.

## Acceptance required for execution support

Retain one portable process record with:

- Bridge, Inspect, Task Standard and dependency versions, source revisions,
  immutable image digest, task family/version and sample ID.
- Task instructions and configuration hashes; declared permissions, sandbox
  configuration, setup and cleanup outcomes. Keep credentials out of the record.
- Original `.eval` hash, exported JSON hash and conversion method. Changed
  export bytes and changed archive bytes are separate drift events.
- Solver identity, reported submission, score and errors, with source locations.
  Keep protected scoring material separate from what the solver can read.
- Known-correct, known-wrong and no-submission controls. Manual scoring must
  remain manual or unknown; an always-success scorer must fail the controls.
- Observation coverage and missing evidence, alongside each bounded result.

Format compatibility, faithful task execution, score correctness and independent
assessment are separate checks. Preserve negative runs, unsupported resources
and cleanup failures in the packet. Do not silently replace the task image or
refresh expected scores to recover a passing result.

See [Independence](INDEPENDENCE.md) for the claims a byte witness, repeat run or
review receipt can support. Neither this reference contract nor an imported
Inspect log is a METR endorsement, security certification or deployment gate.
