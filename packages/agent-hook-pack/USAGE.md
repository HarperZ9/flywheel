# Usage

`agent-hook-pack` is a small, dependency-free utility that ships a set of
public-safe local hooks and a CLI to inventory, audit, and install them. It also
exposes a tiny importable Python API.

Requires Python 3.10+.

## Install

From a clone of the repository:

```bash
python -m pip install -e .
```

This installs the `agent-hook-pack` console script.

## CLI

```text
usage: agent-hook-pack [-h] [--source SOURCE] [--target TARGET] [--version]
                       [{audit,install,list,path}]
```

Commands:

| Command   | What it does                                                         |
| --------- | ------------------------------------------------------------------- |
| `audit`   | Inventory + sanity-check the hooks (default when no command given). |
| `list`    | Print the discovered hook file names.                               |
| `install` | Copy the packaged hooks into a target directory.                    |
| `path`    | Print the absolute path of the packaged hook directory.             |

Options:

- `--source SOURCE` -- directory to read hooks from. Defaults to the packaged
  `hooks/` directory inside the installed package.
- `--target TARGET` -- directory to install hooks into. Defaults to
  `.claude/hooks`. Only used by `install`.
- `--version` -- print the package version and exit.

`audit` exits `0` when no problems are found and `1` when it reports findings.
The other commands exit `0` on success.

### What `audit` checks

For the chosen source directory it verifies:

- all five required hooks are present
  (`block-secrets.py`, `check-branch.sh`, `check-env-sync.sh`,
  `lint-on-save.sh`, `verify-no-secrets.sh`),
- no hook file is empty,
- each hook has a shebang and the shebang matches its runtime
  (`.py` → python, `.sh` → bash/sh),
- no obvious credential-shaped strings appear in any hook
  (GitHub `ghp_…`, OpenAI-style `sk-…`, AWS `AKIA…`, PEM private-key headers).

Each finding is printed as `<path>: <issue>`.

## Worked examples (CLI)

> Output below is illustrative. It was produced by running the commands in this
> repository; absolute paths will differ on your machine.

### 1. List the packaged hooks

```bash
agent-hook-pack list
```

Expected output:

```text
block-secrets.py
check-branch.sh
check-env-sync.sh
lint-on-save.sh
verify-no-secrets.sh
```

### 2. Audit the packaged hooks

```bash
agent-hook-pack audit
```

Expected output (clean inventory, exit code `0`):

```text
findings: none
```

`audit` is also the default, so bare `agent-hook-pack` does the same thing.

### 3. Install the hooks into a project

```bash
agent-hook-pack install --target .claude/hooks
```

Expected output:

```text
copied 5 hook file(s)
```

The five hook files are written into `.claude/hooks/` (the directory is created
if it does not exist).

### 4. Print the packaged hook directory

```bash
agent-hook-pack path
```

Expected output (path will differ on your machine):

```text
/path/to/site-packages/agent_hook_pack/hooks
```

## Importable Python API

The same behavior is available from `agent_hook_pack.hook_pack`:

```python
from agent_hook_pack import hook_pack

# Discover hook files (defaults to the packaged hooks/ directory).
hooks = hook_pack.discover_hooks()
print([p.name for p in hooks])
# -> ['block-secrets.py', 'check-branch.sh', 'check-env-sync.sh',
#     'lint-on-save.sh', 'verify-no-secrets.sh']

# Audit a directory. Empty list means no problems.
findings = hook_pack.audit_hooks(hook_pack.HOOK_DIR)
print(findings)
# -> []

# Install the packaged hooks into a target directory; returns the count copied.
count = hook_pack.install_hooks(hook_pack.HOOK_DIR, ".claude/hooks")
print(count)
# -> 5
```

Useful module attributes:

- `hook_pack.HOOK_DIR` -- `Path` to the packaged hook directory.
- `hook_pack.EXPECTED_HOOKS` -- the set of required hook file names.
- `hook_pack.HOOK_EXTENSIONS` -- recognized hook extensions (`.py`, `.sh`).
- `hook_pack.SENSITIVE_PATTERNS` -- credential-shaped regexes used by the audit.

The package version is exposed as `agent_hook_pack.__version__`.
