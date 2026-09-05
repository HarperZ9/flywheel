# Contributing

Flywheel is an epistemic verification engine. It decides whether a claim is
supported by evidence, and it refuses to say more than the evidence carries.
Contributions are held to the same rule as the code: a result nobody can
re-derive is not a result.

One person maintains this. The scarce thing is not effort, it is a second
machine. Every "it works" here was observed on one Windows workstation.

## The most useful thing you can send

Run it somewhere else and say what happened.

```bash
python -m pip install flywheel-verify
flywheel lanes --probe
```

The roster reads 14 of 14 live on the maintainer's machine, and two of those
lanes resolve through a local source checkout rather than an installed package.
Nobody knows what a clean install does on Linux or macOS, and a report saying it
does not work is worth more than one saying it does.

Post the result to `findings` on the board at
`https://bulletin.zaindharper.workers.dev`, or open an issue here. The board
lists this and other open items at `/.well-known/agent-work.json`.

```
bulletin-report:v1
item: flywheel-lane-roster-off-one-workstation
platform: linux x86_64
runtime: python 3.12.4
result: partial
command: flywheel lanes --probe
observed: 12 of 14 lanes answered; canon and mneme reported not installed
```

The keyed lines exist so many reports become a number with a denominator rather
than a pile of anecdotes.

## Opening a pull request

Fork, branch, and open it against `main`. A person reads every change.

```bash
python -m pip install pytest pytest-timeout pynacl pillow numpy scipy
python -m pytest tests/test_<the_feature_you_touched>.py -q
```

Run the slice that covers what you changed, not the whole suite. The full
collection is 6908 tests across 549 files and takes long enough that nobody runs
it while iterating. Continuous integration shards it four ways and runs all of
it for you.

## Gates that surprise people

These run on every pull request and each one is runnable locally. A red here
usually means a rule you had no way to guess, so the command is listed rather
than left for the log.

| What it checks | Run it |
| --- | --- |
| No source file over 300 lines, and the burn-down list only shrinks | `python scripts/check_file_gate.py` |
| The accept path imports nothing outside the standard library | `python scripts/check_verifier_stdlib.py` |
| A published repository's instructions name no local path | `python scripts/check_public_instructions.py` |
| No checker claims optimality on a public surface | `python scripts/check_claim_language.py` |
| Hard prose rules on the calibrated files, including no em dashes | `python scripts/check_writing.py --gate README.md` |
| The disproof gate runs on a bare interpreter with nothing installed | `python -m harness.cli_entry gate` |

The verifier also runs one Python version below the package floor, because the
accept path is what a stranger runs to check our work and it has to survive an
old interpreter.

## What a good change looks like

- A test that fails without it, named for the thing that would break in the
  world rather than the function that was edited.
- A claim bounded by what was measured. A number arrives with its denominator,
  its interval, and what it does not prove.
- An honest null kept rather than removed. "No uplift claimed" is a result.
- A comment saying why, where why is not obvious. Comments restating the code
  are noise.

Changes that widen what the engine will assert need the evidence to go with
them. A verifier that accepts more is not an improvement until something shows
the wider set is still correct.

## What a fork pull request can reach

Nothing beyond the checkout. Workflows here trigger on `pull_request`, run on
GitHub-hosted runners, and reference no repository secrets, so a fork builds
with a read-only token. No agent has write access. That is what makes an open
invitation safe to publish rather than a risk being accepted.

Tags are the exception and they are not yours to push: a `v*` tag publishes to
PyPI and builds the installer. Version bumps are a maintainer action.

## Security

Report anything exploitable privately rather than in a pull request. There is
no published security policy here yet, so open an issue saying only that you
have something to report and holding back the detail until someone answers.
