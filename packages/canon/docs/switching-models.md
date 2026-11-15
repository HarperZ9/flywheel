# Moving a project between models and tools

You work on one repository with Claude Code in the morning and Codex in the
afternoon, try Cursor for a refactor, and paste context into a chat app or a
local model when you need a second opinion. Each of them starts from nothing,
and you explain the project again: what you are doing, what is still open, what
you decided and what you already tried, and which quirks of the environment
bite. canon keeps that state as records bound to the repository and writes it
into the file each tool reads when it starts.

This guide covers the commands. The specification is
`project-docs/W1-WORKSPACE.md` and the reasoning behind each rule is in
`project-docs/W1-DECISIONS.md`.

## Install

The workspace commands ship in `flywheel-canon` 0.3.0 and later. Install the
release from PyPI:

```bash
python -m pip install "flywheel-canon>=0.3.0"
```

To run the latest `main` instead, install from a checkout of the repository:

```bash
python -m pip install -e .
```

canon needs Python 3.11 or newer and the standard library.

## One project, one store

```bash
cd your-repo
canon workspace id
```

canon derives the project's id from its git remote, so two clones of one
repository share their records and a fork has its own. A local-only repository
gets a random value canon keeps in its `.git` directory. Records live outside
the repository, in `~/.canon/store`, or wherever `CANON_STORE` or `--store`
points.

Two apps cloned from one starter repository share its remote, and with it one
project id. The first command you run in a new checkout prints a notice. If the
checkout is a different project, give it its own name:

```bash
git config canon.project chat-app
```

Every stored record names its project. A read that finds another project's
record in this project's file fails rather than mixing the two, and another
project's records appear in a brief only when you name that project with
`--include-project`. Promoting a record to global scope, where every project
reads it, is an explicit, logged command; copy the id from
`canon workspace list`:

```bash
canon workspace promote <record-id> --reason "house rule for every repository"
```

A promotion is refused when global already holds a record with that id.

If you rename the remote, its id changes. The old records stay in the store;
copy them over with
`canon workspace adopt --from <old-id> --reason "renamed the remote"`.

## Record the state you would otherwise re-explain

```bash
canon workspace focus --goal "Ship the JSON export" --area src/export
canon workspace task "Add the --json flag" --status in-progress
canon workspace task "Update the changelog"
canon workspace decide --title "Keep the CSV writer" \
    --decision "Add JSON beside CSV" --context "Downstream scripts parse CSV" \
    --reject "Replace CSV with JSON" "breaks three downstream scripts"
canon workspace constraint "The Windows runner times out after 10 minutes" --quirk
canon workspace set-status task-2 done
canon workspace list
```

Each rejected alternative is recorded with its reason, and the command refuses
one that arrives without it. The reason is what stops the next agent from trying
that option again.

## Or import what the last session knew

```bash
canon workspace import --from claude-code path/to/session.jsonl
canon workspace import --from codex path/to/rollout.jsonl
canon workspace list --proposed
canon workspace accept <proposal-id>
canon workspace reject <proposal-id> --reason "quoted, not decided"
```

Proposal ids are digests, so copy them from `canon workspace list --proposed`.
`accept` refuses a proposal whose record changed after the proposal was made;
compare the two and pass `--force` to accept it anyway.

The importer reads a Claude Code session file or a Codex rollout (Codex 0.32 or
later) and proposes the session's focus, the open steps of its last plan,
`TODO` markers, sentences like "we decided to X because Y", and failed
approaches like "I tried X but Y". Every proposal names the file and line it
came from, and nothing reaches a brief until you accept it.

Before anything is stored, API keys and tokens, private keys, auth headers and
cookies, passwords and tokens in URLs, password fields in config files, and
secret-named assignments in any case (`DB_PASS=`, `aws_secret_access_key = `)
are replaced with `[REDACTED:<rule>]`. The store also refuses any record that
still looks like one.

In a URL, the password in `https://user:password@host` is redacted unless it
is a placeholder such as `<password>` or `${DB_PASS}`. A user part with no
password (`https://NAME@host`) is redacted when it holds a run of eight or
more letters and digits that is not a word followed by a number, such as
`a8f3k2j9x7` or a hex digest. A name such as `git@`, `deploy-bot-2024@` or
`GitHubUser42@`, an email address, a placeholder such as `${TOKEN}@`, and a
port followed by a path, a query or a fragment stay.

Each importer lists what it drops (thinking blocks, tool output, system
entries and more) and counts it in its report. A session with an entry type the
importer has never seen is refused until you declare that drop with
`--drop-type`, so a change in a tool's format shows up as a refusal you can
read. The refusal prints the flag to add, for example
`--drop-type brand-new-entry`. A
session that names a different repository is refused unless you pass
`--accept-foreign-source`.

## Hand off to the next agent

```bash
canon handoff --to codex
canon handoff --to markdown --out BRIEF.md --receipt brief.receipt.json
```

The brief lists the focus first, then open work, then recent decisions with
the alternatives dropped and why, then constraints and quirks. A markdown
brief has no instruction file to carry your instruction blocks, so it leaves
them out and says how many on stderr (in `--json`, as `omitted_blocks`). It fits the
target's size budget; anything that does not fit is left out whole, counted,
and named as far as the budget allows in a `Left out` section at the end, and
the receipt names every one. The receipt also holds digests of the brief and
of the records behind it.

## Switch in one command

```bash
canon switch --to claude-code --create --dry-run
canon switch --to codex --create
canon workspace targets
```

`--create` makes a missing file. To let canon write into a file you already
have, add these two lines where canon may write, then switch:

```
<!-- canon:begin scope=workspace -->
<!-- canon:end -->
```

`switch` writes your blocks and the brief into the target's own instruction
file, between canon's markers only, so the agent reads it at startup:

| target | file |
|---|---|
| `claude-code` | `CLAUDE.md` |
| `codex` | `AGENTS.md` |
| `gemini-cli` | `GEMINI.md` |
| `copilot` | `.github/copilot-instructions.md` |
| `cursor` | `.cursor/rules/canon.mdc` |
| `markdown` | none; the brief is printed to paste anywhere |

A file with no canon region is left alone until you add the markers, and
`--create` makes a missing file with an empty region. canon refuses to write an
`AGENTS.md` larger than Codex reads, because Codex would cut its tail, and it
refuses a switch to Codex while an `AGENTS.override.md` sits beside it, because
Codex would read the override instead. `--receipt FILE` writes the list of
every record the brief left out.

If you or an agent edit inside canon's region, the next `switch` keeps the
edit. Each edit becomes a proposal and the switch waits until you accept or
reject it. `canon workspace pull --from claude-code` reads the edits back and
leaves the target files as they are.

## Limits

- The importers match fixed text patterns. A decision phrased another way is
  missed, and each proposal waits for you to accept it.
- Both session formats belong to their vendors and can change. The importers
  were checked against public sources on 2026-09-23 and refuse entries they fail
  to parse. Importers cover Claude Code and Codex; Gemini CLI, Cursor, ChatGPT
  and Claude web histories are unsupported.
- The scrubber recognises secrets by their shape. A secret with no recognisable
  shape passes through, and email addresses are not redacted. After `Bearer`,
  `Authorization:` or `X-API-Key:`, a word, a number, a date or a path on the
  same line is left alone, so "use bearer authentication" and an OAuth
  `token_type: bearer` line stay as written. After a
  secret-named key, a value shorter than four characters, a value that reads
  as code (`get_token()`, `self.password`, `string`), a number, a date, a path
  and a boolean are left alone, so a numeric PIN after `password=` passes
  through. A value after a password name is redacted even when another word
  follows the password word (`DB_PASSWORD_PROD`, `password_confirmation`),
  unless that word describes the password (`PASSWORD_MIN_LENGTH`,
  `password_policy`). A path after a password or token name needs two
  segments, so `DB_PASSWORD=/hunter2` is redacted. A word of up to ten
  letters after a key or token name is left alone (`token: bearer`), and a
  name where another word follows the key or token word (`token_type`,
  `KEY_COUNT`, `session_token_ttl`) keeps its value unless the value looks
  random: twelve or more characters with no space that hold a run
  of eight or more letters and digits that is not a word followed by a number
  (`a8f3k2j9x7m1`, a hex digest), or that mix both cases with `+`, `/` or
  `=`. An identifier such as `kv-prod-eastus2` or `release-2026-10` is left
  alone, and so is a random value whose digits all come at the end.
- Instruction files load every rule for every file. A block scoped with
  `applies_to` is written with an `Applies to:` line, and the model reads that
  line as advice.
- The brief budgets are canon's defaults; `--budget-bytes` and `--budget-lines`
  override them. The host file limits come from each tool's public
  documentation and can change. For Codex, canon reads `project_doc_max_bytes`
  from `config.toml` where Codex reads it (under `CODEX_HOME` when that is set,
  else under `~/.codex`), so a limit you raised there is the one canon refuses
  at, and the refusal names the setting.
- The store trusts the local filesystem. Isolation keeps projects from mixing,
  and anyone who can write the store directly can change it.
- The brief shows what was recorded or imported. Work from an unrecorded
  session is missing from it.
