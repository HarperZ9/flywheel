# CLI reference

The command is `articulate`. With no file, a command reads standard input. A
profile is chosen by an explicit flag, then an in-file `writing-profile:` tag,
then the file path, then the default.

## check

Screen one or more files and report the findings.

```bash
articulate check [FILE ...] [--profile P] [--mode M] [--gate] [--json]
                 [--sarif] [--verbose] [--spans] [--content-free]
```

- `--profile P`: force a register profile or a domain profile
  (`ux-microcopy`, `code-review`, `plain-language`, `controlled-english`,
  `rfc-keywords`, `product-copy`, `note`, `author-voice`, `publication`,
  `outbound`). A domain profile adds its rule pack's findings; see
  [Domain profiles](features.md#domain-profiles).
- `--mode M`: a writing mode, for example `memo/argue`. A mode wins over profile
  inference.
- `--gate`: exit 0 when every file is screened and passes, and 1 when any file is
  blocked or fails to screen.
- `--json`: a machine-readable payload with findings, cadence, and the verdict.
- `--sarif`: SARIF 2.1.0 for GitHub code scanning, Azure DevOps, and reviewdog.
- `--verbose`: expand the LOW advisories to line numbers.
- `--spans`: per-paragraph findings, so a paragraph dense with devices is flagged
  in place. A flag marks style; it leaves authorship open.
- `--content-free`: omit every verbatim substring and exact offset from the
  console, JSON, and SARIF output.
- `--config PATH|none`: the project config. By default the nearest
  `.articulate.json` above each file is read; for standard input the search
  starts in the current directory. `--config none` turns discovery off. See
  [Project config](features.md#project-config).

A project config's terminology findings print with their rule id, for example
`[HIGH terminology/banned/whitelist]`. The profile is chosen by `--mode`, then
`--profile`, then an in-file `writing-profile:` tag, then a glob in the project
config, then the file path, then the default. `score`, `receipt`, `plan`,
`judge`, `fix` and `polish` take `--config` too. A malformed config exits 2 with
the file and the reason.

## score

Print the graded texture score and the verdict on one line per file.

```bash
articulate score [FILE ...] [--profile P] [--mode M]
```

```text
$ articulate score docs/getting-started.md
[articulate] docs/getting-started.md [flavored]: verdict clean, texture 0/100 (low), gate ok [0H/0M, 916w]
```

## receipt

Emit a re-derivable receipt as JSON on standard output.

```bash
articulate receipt [FILE ...] [--profile P] [--spans]
                   [--redact {none,drop,hash}] [--reviewer NAME]
```

- `--spans`: record the per-paragraph verdicts in the receipt.
- `--redact drop`: a content-free audit receipt with the matched substring and the
  offsets dropped.
- `--redact hash`: as `drop`, plus a hash of the match for an equality check
  against a known string. Read [hash mode](boundaries.md#hash-mode-supports-an-equality-check) first.
- `--reviewer NAME`: record who screened it. When the flag is absent, the CI
  actor fills the field if one is set.

## verify

Replay a receipt against text and return the verdict.

```bash
articulate verify RECEIPT FILE
```

The exit code is 0 for `Match`, 1 for `Drift`, and 2 for `Unverifiable`.

## audit

Query a directory of committed receipts locally.

```bash
articulate audit [PATH ...] [--days N] [--reverify] [--gate] [--json]
```

- `PATH`: receipt files or directories. The default is the current directory.
- `--days N`: the recent-activity window for the summary. The default is 30.
- `--reverify`: replay each receipt against its source file, and report `Match`,
  `Drift`, `source-changed`, `source-missing`, or `source-unreadable`.
- `--gate`: with `--reverify`, exit 1 when any source drifted, changed since it
  was screened, or failed to read. A sub-threshold or stale-ruleset
  `Unverifiable` is reported and leaves the gate passing.
- `--json`: the summary as JSON.

## config

Show which project config applies to a file, the profile it chooses and why,
and what the config sets.

```bash
articulate config [PATH] [--config PATH|none] [--json]
```

The text form prints the config path, the profile and its source (for example
`config glob 'notes/**'` or `path inference`), the banned, preferred and allowed
terms, the freeze terms and the rule-pack options. `--json` prints the same
fields as an object. A malformed config exits 2 with the file and the reason.

## modes

List the available writing modes.

```bash
articulate modes
```

## process

Keep a local, opt-in record of your own process. See the
[feature reference](features.md#the-process-record).

```bash
articulate process init DOC [--track] [--opt-in words,diff,time,snapshot]
articulate process draft DOC
articulate process note DOC (--text-file F | --label L) [--shareable]
articulate process source DOC CITATION [--shareable]
articulate process assist DOC --tool T --verb {generated,drafted,edited,translated}
                          [--sections S,...] [--model M] [--version V]
                          [--source-type CODE --languages SRC,TGT]
articulate process input DOC --method M [--sections S,...]
articulate process review DOC --role R --reviewed W --outcome O [--editorial] [--name N]
articulate process anchor DOC [--commit ID | --token-sha256 H]
articulate process continue DOC --reason R
articulate process export DOC [--include F,...] [--reveal N[=FILE]] [--contributions F]
articulate process verify (DOC | SUMMARY.json)
```

`export --include` names the fields a default export leaves out: `words`, `diff`,
`time`, `labels`, `citations`, `review_names` and `input_method`. `continue` is
for a broken log. `verify` reads a file as a summary when its `schema` field
says so, whatever its name; on a document it reports `intact` (exit 0),
`broken` (exit 1) or `missing` (exit 3). A missing log is no record: "an absent or
short record shows nothing about a writer". `verify`, `export` and `disclose`
each print that limits line.

## disclose

Write a statement of tool use and contributor credit from the process log.

```bash
articulate disclose DOC [--template {general,pip}] [--contributions F]
                    [--include input_method] [--claim SENTENCE]
```

It writes a statement that matches the log. When the log is missing or broken,
or the request would misstate the log, it exits 2 and leaves the files as they
are.

## desk

Prepare the questions a reviewer should ask, inside the document and across the
field.

```bash
articulate desk FILE [--venue {none,paper,course}] [--disclosure F] [--author] [--json]
```

An unknown `--venue` exits 2 with the list of venues. The JSON output carries a
`scope` line that says what the report covers.

## Editor commands

The main CLI exposes model editing and deterministic fixes:

```bash
articulate judge FILE --backend auto --json
articulate fix FILE --backend none --out edited.md
articulate polish FILE --backend ollama --json
```

All three accept `--backend auto|host|sampling|anthropic|claude-cli|openai|ollama|none`,
`--mode M`, `--profile P`, `--config PATH|none`, `--out OUT` and `--json`. A
project config's terminology and pack options travel in the edit plan, and its
freeze terms are protected in every rewrite. `fix` and `polish` also take
`--allow-change KINDS` and `--explain [json|text]`, described below. Sampling requires an MCP
session that advertised sampling, so it works from an MCP client. `host` returns
a plan for a calling model to complete. With no model, `none` makes conservative
mechanical fixes and reports remaining findings; its judge reports local findings
and rule reasons. Inspect the gate
and refused spans even when a call succeeds.

The legacy entry point remains available:

```bash
python -m articulate.editor --judge FILE --backend auto
python -m articulate.editor --fix FILE --backend none --out edited.md
python -m articulate.editor --polish FILE --backend ollama --mode memo/argue
python -m articulate.editor --review FILE
```

### plan and submit

Use the calling agent's own model, through the account it already has:

```bash
articulate plan FILE [--mode M] [--profile P] [--goal fix|polish|judge]
                     [--is-html] [--is-tex] [--allow-change KINDS]
                     [--config PATH|none]
articulate submit FILE REWRITE --plan PLAN_ID [--scores JSON] [--model NAME]
                  [--explain [json|text]]
```

`plan` writes JSON with the local findings, their reasons, the hardened model
instructions, masked text, protected spans and a plan ID. Give the model those
instructions and the masked text. Save its output as `REWRITE`, then submit it
with the unchanged original `FILE` and the plan ID. Keep mask tokens intact.
The optional model name is caller-reported attribution. `--scores` accepts a
JSON object with `before` and `after` objects, each holding integer scores from
1 to 5 for `concreteness`, `commitment`, `economy`, `rhythm` and `restatable`.
For polish, these scores support the quality non-regression check. Without
them, quality is reported as `unassessed`; gate and span checks still apply.
Mode, profile, goal and mask settings are carried in the plan ID and need not
be repeated on submission.

Submission checks the source and plan configuration against the plan ID,
restores masks and runs the meaning guard. Protected numbers, URLs, citations,
code, math and quotations must survive; refused spans retain their original
wording and report a reason. The result includes accepted text, gates before
and after, per-rule deltas and a host receipt. A matching plan ID binds inputs;
it is not authentication or proof of semantic equivalence. A plan and its
result can contain source text, so store them with the document's protections.

### Allowing a protected change

The guard keeps a paragraph whose protected content changed. When an edit
needs to change a number or a link on purpose, name that kind:

```bash
articulate fix FILE --backend none --allow-change number,url
articulate plan FILE --allow-change number
```

`--allow-change` takes a comma-separated list on `plan`, `fix` and `polish`.
The kinds that can be allowed are `citation`, `code`, `link`, `modal`,
`negation`, `number`, `number-range`, `quantity`, `quote`, `scope`, `term` and
`url`. A change of an allowed kind is accepted and listed in `allowed_changes`
(paragraph and kind) in the result and in the editor receipt. A change of any
other kind makes the guard keep the original paragraph. Disclosure lines, an added first-person
sentence, HTML and math can never be allowed; naming one exits 2 with the list
of kinds that can be. The plan binds the allowed kinds, so `submit` cannot
widen them. A plan with no allowed kinds and no frozen terms keeps the v2 plan
schema and the same plan ID as before.

### The change report

```bash
articulate fix FILE --backend none --explain          # adds "changes" to the JSON
articulate polish FILE --explain text                  # prints a readable report
articulate submit FILE REWRITE --plan PLAN_ID --explain
```

`--explain` on `fix`, `polish` and `submit` reports each changed sentence. It
pairs the sentences of the original and the accepted text paragraph by
paragraph. For each changed pair it gives the text before and after, the
findings (rule id and label) on the old sentence that are gone, those that
remain, and any the new sentence adds. It also lists each paragraph the guard
kept, with its reasons, and each allowed change. `--explain` or
`--explain json` adds this as `changes` to the result JSON; `--explain text`
prints the report in place of the JSON. The MCP `fix`, `polish` and
`edit_submit` tools take `explain: true` for the same report. The findings
columns show what the checker saw. The report carries a `scope` line that says
what the pairs cover.

### Backend configuration

Use `--backend` to select a backend for one call, or set `ARTICULATE_BACKEND`
for the process. The default is `auto`.

- `host`: the calling model uses `plan` and `submit`; text follows the calling
  host's model policy.
- `sampling`: the MCP client must advertise sampling at initialization; text
  goes to the host's selected model.
- `anthropic`: `ANTHROPIC_API_KEY`, with optional `ARTICULATE_MODEL`; text goes
  to Anthropic's Messages API. The default model is `claude-sonnet-5`.
- `claude-cli`: an installed, authenticated Claude CLI, with optional absolute
  `ARTICULATE_CLAUDE_CLI` path; text goes to its provider.
- `openai`: `ARTICULATE_OPENAI_BASE_URL`, `ARTICULATE_OPENAI_API_KEY` and
  `ARTICULATE_MODEL`; text goes to the configured compatible endpoint.
- `ollama`: `ARTICULATE_OLLAMA_URL` and `ARTICULATE_LOCAL_MODEL`; text goes to
  the configured Ollama server.
- `none`: runs offline with mechanical edits; needs no account or model.

In MCP, `auto` uses sampling when advertised, otherwise returning a host edit
plan before trying a separately billed backend. The calling model can complete
that plan with `edit_submit`. In the plain CLI, automatic selection tries
configured Anthropic, the Claude CLI, configured OpenAI-compatible endpoints,
Ollama and `none`, recording failures before continuing. Explicit backend
selection tries the requested route first, then the automatic fallback chain.
Use local-only mode to constrain where fallback can send text.

`OPENAI_API_KEY` is accepted for the default OpenAI address. A custom compatible
endpoint, including vLLM or LM Studio, uses `ARTICULATE_OPENAI_API_KEY`; an
unrelated OpenAI key is not forwarded to it. `ARTICULATE_MODEL` is required
for every OpenAI-compatible endpoint, including the default OpenAI address.

Ollama defaults to `http://127.0.0.1:11434`. With `ARTICULATE_LOCAL_MODEL` unset,
it inspects installed models through `/api/tags`, preferring `qwen3:8b`,
`qwen2.5:7b`, `llama3.2:3b`, then `gemma3:4b`, then the first installed model.
It uses models already pulled.

Set `ARTICULATE_LOCAL_ONLY=1` to keep editing on Ollama at a loopback address or
`none`. The editor backend selector refuses hosted routes, host and sampling
before a connection. `plan` and `submit` run their checks locally; a document
already in a host's conversation follows that host's data policy. For
deterministic editing alone, use `--backend none`.

For the Claude CLI, `ARTICULATE_CLAUDE_CLI` must be an absolute executable path;
otherwise Articulate searches absolute PATH entries and skips the current
folder. Authentication is checked before the model call. A credit, login or
rate-limit failure records a reason and allows automatic selection to continue.
To repair an account failure, use `claude login` with the intended subscription
account, configure `ANTHROPIC_API_KEY`, or choose Ollama or `none`.

The CLI child runs in a private empty temporary folder with user settings only,
using `--setting-sources user --strict-mcp-config --tools ""`. Document-folder
settings stay out. On Windows, `NoDefaultCurrentDirectoryInExePath=1` keeps the
npm shim's `node` lookup on PATH. An older CLI that rejects these flags is
reported as unavailable. The text still goes to the CLI's hosted provider.

## house

```
articulate house apply [FILE | -] [--json] [--receipt OUT]
articulate house brief [--agents]
articulate house show
articulate house on | off
articulate house set KEY=VALUE...
```

`apply` runs the house transform on model output and prints the result; notes
go to standard error. `--receipt` writes an `articulate/house-receipt/v2`
receipt that `articulate verify` replays. `brief --agents` prints the brief as an
AGENTS.md section. `on`, `off` and `set` write the settings file and nothing
else. Keys for `set`: `mode`, `length`, `headings`, `lists`, `first_person`,
`limits`, `end_line`. See [the house voice](house-voice.md).

## voice

```
articulate voice learn SAMPLES... --name N --mine [--no-vocabulary]
articulate voice show N | list | path | identity [--name DISPLAY]
articulate voice compare DRAFT... --name N
articulate voice apply DRAFT --name N --authored-by-me [--author-text FILE] [--out FILE]
articulate voice submit DRAFT REWRITE --plan ID [--author-text FILE] [--out FILE]
articulate voice export N --out FILE
articulate voice import FILE [--adopt-identity]
articulate voice delete N | --all
articulate voice intend [--goal G] [--audience A] [--stance S] [--sample FILE]... [--base NAME]
                        [--tool NAME]... [--name N] [--out FILE] [--json] [--list]
articulate voice check DRAFT... --intent SPEC|NAME [--min-score N] [--json]
```

`voice check` exits 1 when a draft scores under `--min-score`; see
[a voice built from intent](voice-intent.md). Every verb takes `--dir` for the store folder. See
[series review and your own voice](series-and-voice.md).

## corpus, titles, interview, restructure

```
articulate corpus FILES... [--single] [--keep FILE] [--json] [--receipt OUT]
articulate titles FILES... [--titles FILE] [--answers FILE]
articulate interview DOC [--voice N] [--out FILE] | --collect FILE [--answers-out FILE]
articulate restructure DOC [--out FILE] [--anchors footnote|link]
```

All four report or propose. They write the files you name with `--out`,
`--receipt` or `--answers-out`, and leave input files as they are.

## dialogue

```
articulate dialogue FILES_OR_DIRS... [--voices DIR] [--format auto|lwd|colon|play]
                    [--theme WORDS] [--min-lines N] [--worst N] [--json]
                    [--markdown FILE] [--gate] [--max-epigram-rate R] [--min-lift X]
```

Checks spoken lines against the dialogue profile and each character's voice
sheet, and scores how distinct each voice is by blind attribution. Prints a
table per character and the worst lines, or the full report with `--json`.
`--gate` exits 1 when the report fails. See [dialogue and character voice](dialogue.md).

## negation

```
articulate negation FILES_OR_DIRS... [--profile NAME] [--rule copy|fiction]
                    [--min-words N] [--all] [--json] [--gate]
```

Finds entries that spend their words on what a thing lacks. An entry is a
paragraph, list item, HTML block, README section, script block, dialogue line
or UI string. Each entry splits into clauses, and the score is the share of
clauses whose main job is negation, limitation or disclaimer, such as "does
not", "never", "no server", "not yet", "only" and "limited to". The output also
gives the share of words those clauses hold, and it lists virtue phrases such
as "provenance", "receipts" and "verifiable" when an entry uses them to sell.

The copy rule warns at 30% and fails at 50%. The fiction rule warns at 45% and
fails at 65%, and it skips character speech, so a character can say no while
narration still counts. Narrative and genre profiles take the fiction rule;
`--rule` picks one directly. Readers cover Markdown, HTML, Low Water `.lwd`
scripts, JSON (a `lines` list reads as one film segment) and JavaScript string
literals. `--gate` exits 1 when any entry reaches the fail line.

## devices

```
articulate devices FILES... [--only DEVICE,...] [--json | --speak | --ssml]
```

Lists the rhetorical devices in each file with their lines: antithesis,
tricolon, anaphora, chiasmus, alliteration, assonance, polysyndeton, asyndeton,
anadiplosis, epizeuxis, isocolon, zeugma and oxymoron. `--only` limits the
report to named devices. `--speak` prints a script to read aloud and `--ssml`
the same script as SSML 1.1. The command never gates; it exits 2 only when a
file cannot be read or a device name is unknown. See [devices](devices.md).

`articulate check --speak` prints check findings as the same kind of script.

## Exit codes

- `check --gate`: 1 if any file is blocked or unscreenable, else 0.
- `verify`: 0 Match, 1 Drift, 2 Unverifiable.
- `audit --reverify --gate`: 1 on a real integrity break, else 0.
- `articulate.bench`: the number of misclassified files, so 0 is a perfect run.
