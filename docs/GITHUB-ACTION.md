# Flywheel in GitHub Actions

The repository is also a GitHub Action. It installs Flywheel, runs one
`flywheel code -p` request on the checked-out repository, and keeps the result
and the session's hash-chained ledger as a workflow artifact, so a reviewer can
see every tool call the run made and recheck the chain later.

```yaml
jobs:
  fix:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: HarperZ9/flywheel@v1.9.0   # or a commit
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        with:
          prompt: "fix the failing test in tests/test_parser.py"
          mode: edit
          test-cmd: "python -m pytest -q"
```

The action ships from 1.7.0 on; pin a release tag or a commit.
The step fails when the request's
test gate fails or no model answers.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `prompt` | required | the request for the agent |
| `mode` | `edit` | `plan`, `edit` or `auto`; `ask` refuses every write here, since nobody can answer |
| `version` | latest | `flywheel-verify` version to install |
| `package` | empty | a pip requirement installed in place of `flywheel-verify` |
| `python-version` | `3.12` | Python for the run, 3.11 or newer |
| `working-directory` | `.` | folder the session works in |
| `backend` | `auto` | pin a backend, for example `claude`, `codex` or `gemini` |
| `max-steps` | `25` | step budget |
| `test-cmd` | empty | tests the request must pass before it counts as done |
| `allow-unsandboxed` | `false` | `true` runs commands bare, labeled, on a runner without an OS sandbox |

The output `result` is the path of the `flywheel.code-result/v1` JSON. The
artifact `flywheel-code-<run id>-<attempt>` holds that file and the session
folder.

## What to know before using it

- The model key comes from your repository secrets through `env`. Flywheel sends
  it only to that provider. The content of the request, and the files and tool
  output the agent reads, go to the provider you pick.
- Inputs reach the step scripts only through environment variables, so a prompt
  that contains shell syntax is passed as text.
- On a Linux runner, commands need bubblewrap for the OS sandbox. Without it
  they are refused unless `allow-unsandboxed` is `true`. File edits do not
  need the sandbox.
- The action does not commit or push. Add your own step to open a pull request
  from the changes if you want one.
- The repository's own CI runs this action against a scripted model on every
  change to it (`.github/workflows/action-smoke.yml`).
