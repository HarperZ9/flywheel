# Review a Norvane capture offline

`flywheel import-norvane` converts an existing Norvane JSON capture into a
content-minimized review and ordinary Journey v2 events/projection. It helps a
reviewer distinguish a reported fix, captured shell outcomes, missing evidence
and the final narrative. It does not run the environment or grade model honesty.

This optional command ships inside `flywheel-verify`; no extra dependency,
provider credential, Docker installation or server is required. It performs no
network calls, commands, task-module imports, filesystem restoration, Journey
store mutations or Bulletin publication. The source files remain unchanged.

## Supported source

The adapter pins the JSON shape in Agent Interpretability Environments commit
`56fd0c11e6cb973b9e1f752ba7c1f35ec3f570bb`, package version 0.1.0:

- `environments/norvane/states.py`: state and terminal score fields.
- `environments/norvane/agent.py`: two pre-executed prefix commands.
- `environments/norvane/run_step.py`: command/output capture and score timing.
- `src/agent_interp_envs/checkpoint.py`: `step-N/state.json` and `messages.json`.

Source: [Agent Interpretability Environments](https://github.com/gkroiz/agent-interp-envs).
The commit is a supported format declaration, not a verified origin identity.
Other revisions are rejected until compatibility is assessed. No upstream code,
paper figures, rollouts or datasets are executed or bundled. Tests contain
newly authored synthetic captures, not model evaluation results.

## Import

Keep the original capture private and quiescent. Place a declaration outside it:

```json
{
  "schema": "flywheel.norvane-capture-source/v1",
  "source_commit": "56fd0c11e6cb973b9e1f752ba7c1f35ec3f570bb",
  "last_step": 3,
  "files": {
    "step-2/state.json": "<SHA-256 of original bytes>",
    "step-2/messages.json": "<SHA-256 of original bytes>",
    "step-3/state.json": "<SHA-256 of original bytes>",
    "step-3/messages.json": "<SHA-256 of original bytes>",
    "final/score.json": "<SHA-256 of original bytes>"
  }
}
```

Replace the digest placeholders with hashes retained by the collector. The
first checkpoint is step 2, after the two harness-prefilled commands. `last_step`
is the last dumped checkpoint, not necessarily the score's `steps` value:
successful submission writes the score before incrementing the counter;
exhaustion without a report writes it afterward. A resumed partial capture
without its earlier checkpoints stays incomplete. Do not invent those steps.

```console
flywheel import-norvane ./private-capture --source-manifest ./capture-source.json
```

The command writes JSON to stdout only. Redirect it to a private destination if
needed. It does not approve the resulting data for publication. Numeric/boolean
score fields remain exactly reported. Text, command strings, arbitrary paths
and transcripts stay in the source capture; output carries fixed relative
artifact names, JSON pointers and value digests. For example, inspect
`step-3/state.json` at `/commands_executed/2/output` locally. These are data
references, never commands. This is content minimization, not an anonymity or
secret-detection guarantee: digests and outcome metadata can reveal information.

Python callers can use:

```python
from harness.norvane_capture import import_norvane_capture

review = import_norvane_capture(
    capture_root, source_manifest,
    imported_at="2026-09-09T23:00:00Z",
    expected_manifest_sha256=held_digest,  # optional
)
```

`held_digest` is the SHA-256 of the declaration's **canonical JSON**, generated
with `harness.evidence_json.canonical_sha256`, not its pretty-printed file bytes.
Retain it separately before transferring or modifying the capture. The CLI
equivalent is `--expected-manifest-sha256`. A value taken from the same untrusted
capture adds no independent authenticity. The adapter labels this a caller-held
assertion even when it matches; origin authentication always remains unavailable.

## Interpret the result

| Field | What it establishes |
|---|---|
| `reported` | Upstream numeric/boolean fields plus references to withheld values. No score is upgraded. |
| `recomputed` | Recorded shell success/failure counts and bounded cross-file consistency. |
| `manifest_file_consistency` | Observed file bytes match caller-declared digests, or mismatch/unavailable. |
| `artifact_integrity` | Match requires matching file digests and the supplied declaration anchor. This does not authenticate the collector. |
| `evidence_completeness` | Presence/consistency of declared JSON checkpoints only. It excludes filesystem snapshots and unobserved actions. |
| `commands[].origin` | Harness prefix/live-model classification reported by the pinned format, not authenticated authorship. A missing prefix yields unknown. |
| `report_consistency` | Always `review_required`: free prose is not classified by keywords or an unvalidated judge. |
| `projection.verdicts` | The report-support claim remains `UNVERIFIABLE`. Hash consistency cannot prove it. |

The native `num_test_invocations_passed` counts zero-return-code shell commands.
`pytest; echo done` can finish successfully after pytest fails. Therefore even
an internally consistent green score does not establish a passing test suite.
The adapter never labels the suite verified. A fix check also has much narrower
scope than the test suite and is not rerun here.

`issues` exposes mismatched score counters, discontinuous command histories,
unmatched test invocations, inconsistent terminal state and potentially truncated
2000-character output previews. Missing terminal state is not reconstructed from
earlier evidence. All-synthetic controls cover the same failure evidence with
an admission of unavailable verification versus a polished success claim, and a
green counter with freshly recomputed file hashes. Both remain review-required;
the latter exposes the mechanical conflict.

Exit 0 means an import without detected conflicts, not task success. Exit 1
emits the review with detected conflicts. Exit 2 is rejected input with a generic,
content-free error. Read missing evidence and the four-way Journey verdict even
when the process exits zero.

## Bounds and filesystem boundary

Only `final/score.json` and `step-2` through declared `step-N` JSON state/messages
files are opened. N is at most 33; other files are not traversed or inspected.
Each file is at most 1 MiB; total input bytes are at most 8 MiB. State command
and test lists are capped at 256 records; transcripts at 4096 messages. JSON
rejects duplicate keys, nonfinite numbers, unexpected state/score keys, coerced
types and excessive nesting. Declarations are capped at 64 KiB.

Reads use the existing `private_artifact_fs` handle-relative reader in read-only
mode. Links/reparse points, irregular files, unsupported filesystem admission,
unsafe ancestry or detected concurrent changes fail closed. The adapter has no
pathname-based fallback. This inherits that primitive's supported-platform limits;
it does not assert protection against a compromised OS or a collector that
fabricates a completely consistent capture. Per-file checked reads are not a
transactional snapshot of the whole directory. A trusted collector-held manifest
helps detect cross-file changes; stop capture writers before importing.

No automatic store append is performed. `events` already use
`flywheel.evidence-journey-event/v2`, and `projection` comes from the existing
`reduce_events` reducer. Authenticated mutation, admission and public projection
remain separate existing operations with their own permissions.

## Upstream attribution

The two exact command identifiers and field contract are adapted from the pinned
Norvane environment. The applicable upstream notice is retained below.

MIT License

Copyright (c) 2026 Aditya Singh, Gerson Kroiz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
