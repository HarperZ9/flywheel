# CrewAI `kickoff_for_each` Replay Audit

This is a public-safe evidence bundle for CrewAI commit `b3aaaab023a53a08db4d36c9430b3463f1efcc7d` (version 1.15.6).

## Result

The documented synchronous, non-streaming contract is `DRIFT`: after one `kickoff_for_each` call over two inputs, unmodified code deletes the most recent run's replay records. The ordinary-`kickoff` control passes.

The local candidate removes one terminal reset. It passes:

- focused regression: 1/1;
- focused control: 1/1;
- focused combined: 2/2;
- existing `kickoff_for_each` selection: 8/8;
- existing replay selection: 9/9;
- focused Ruff, formatting, diff, and patch checks.

This bundle does not claim an upstream fix. At evidence-capture time, this audit had created no upstream issue, pull request, commit, or push. Publishing the evidence bundle does not change upstream code.

## Reproduce

Use a clean checkout at the pinned commit with Python 3.12:

```powershell
git clone https://github.com/crewAIInc/crewAI.git crewAI
cd crewAI
git checkout --detach b3aaaab023a53a08db4d36c9430b3463f1efcc7d
uv sync --python 3.12 --frozen --group dev
```

Copy `test_kickoff_for_each_replay.py` to `lib/crewai/tests/`, then run the regression and control on unmodified production code:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -n 0 --tb=short --disable-warnings lib/crewai/tests/test_kickoff_for_each_replay.py::test_kickoff_for_each_persists_only_the_most_recent_run_for_replay
.\.venv\Scripts\python.exe -m pytest -q -n 0 --tb=short --disable-warnings lib/crewai/tests/test_kickoff_for_each_replay.py::test_regular_kickoff_persists_and_replays_latest_run
```

The first command should fail because storage is empty; the control should pass. Apply only the production hunk after recording RED:

```powershell
git apply --exclude=lib/crewai/tests/test_kickoff_for_each_replay.py candidate.patch
```

Rerun the focused module:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -n 0 --tb=short --disable-warnings lib/crewai/tests/test_kickoff_for_each_replay.py
```

Expected candidate result: 2 passed.

## Scope

The runtime conclusion covers synchronous, non-streaming `kickoff_for_each` only. Async/streaming variants and full-suite behavior were not evaluated. Removing the reset also means an empty input list preserves an older latest-run store; maintainers should decide that edge contract explicitly.

The test replaces `Task.execute_sync` with deterministic output. Repository network blocking remains active, with exact loopback host patterns allowed for Windows `socket.socketpair`. This is an exercised-path control, not a packet-capture attestation.

## Files

- `AUDIT.md` — human-readable findings and limits
- `canonical-result.json` — structured experiment result
- `action-receipt.json` — Project Telos receipt wrapper
- `candidate.patch` — one-line production remedy plus regression test
- `test_kickoff_for_each_replay.py` — standalone regression/control test
- `logs/` — selected RED, control, GREEN, relevant-suite, and static evidence
- `LICENSE` — upstream CrewAI MIT license
- `SHA256SUMS` — SHA-256 manifest for every public file except the manifest itself

Verify with:

```powershell
python verify_public.py
```
