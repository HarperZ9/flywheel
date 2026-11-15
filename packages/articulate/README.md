<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/articulate/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/articulate/main/docs/art/hero-light.svg" alt="articulate. A fan of ruled sheets drawn in fine lines, the top sheet lit by a bright core. The caption reads: Local writing-quality checker and editor. No network. Not an authorship detector." width="100%">
</picture>

# articulate

Articulate checks prose on your computer. It names each writing pattern it finds and the line it sits on, and a profile for each kind of writing decides which findings block.

```bash
python -m pip install articulate-writing
articulate check README.md --profile readme --gate
```

Python 3.9 or newer. The checker uses only the standard library and needs no model, account or API key.

```text
$ articulate check post.md --profile readme --gate
[articulate] post.md [readme]: 4 high, 2 medium (blocked)  texture 100/100
  L3 [HIGH antithesis] it's not just X, it's Y: This release is not just a bug fix; it is a new foundation. ...
  L3 [HIGH corporate-verb] leverage / underscore / reflect (as corporate verb): ...
  L4 [HIGH filler-intensifier] genuinely / really / truly / actually: ...
```

With `--gate` the command exits 1 when a high finding blocks under the chosen profile, so it drops into CI or a pre-commit hook.

Use it on documentation, READMEs, release notes, essays and commit messages. It flags stacked hedges, marketing words, corporate verbs, contrast framing, rule-of-three lists, em dashes and the rhetorical habits common in model-written text.

Articulate finds writing patterns and shows where they are. Use it to improve writing. Use other evidence to decide who wrote a text. On 183 texts of known origin it flagged all 84 AI texts and 57 of 75 human texts (76%, 95% interval 65% to 84%), including 10 of 18 essays by English learners ([`results.json`](corpus/provenance/results.json)). Teachers: use it to help a student improve a draft, and use other evidence to judge who wrote an essay.

## What it does

- **Check.** Flags rhetorical devices (antithesis, corrective negation, rule-of-three, em dashes, filler intensifiers, corporate verbs), marketing and email register, and plain-style signals such as expletive openers, nominalization density, passive voice, adverb density and uniform cadence. Each run gives a 0 to 100 texture score and a pass or block result.
- **Profiles.** `procedure`, `commit`, `research`, `readme`, `essay`, `narrative` and more set which findings block. Procedures gate strictly and fiction gates nothing. A profile comes from `--profile`, a `writing-profile:` tag in the file, or the file path.
- **Modes and genres.** A mode pairs a register with a purpose, such as `memo/argue` or `technical-docs/explain`. Genres (`literary-fiction`, `genre-fiction`, `ya-fiction`, `memoir`, `screenplay`, `poetry`) read narrative prose by their own conventions, and quoted speech stays out of the device checks. `articulate modes` lists them all.
- **Edit.** `judge` reads problems a pattern rule cannot see, such as a vague claim or a weak verb. `fix` rewrites to the standard and rechecks the result. `polish` loops until the draft clears a quality bar. These use a model you configure, the calling model in an MCP host, or mechanical fixes with no model.
- **Receipts.** `articulate receipt` records a check, and `articulate verify` replays it against the file later. `articulate audit` queries a folder of committed receipts.
- **House voice.** `articulate house on` gives an AI model a published, versioned voice: answer first, numbers with denominators. `articulate house off` turns it off.
- **Your own voice.** `articulate voice learn --mine` builds a profile from files you name. Compare drafts with it, or shape your own draft toward it.
- **A voice from intent.** `articulate voice intend` takes a goal, an audience and a stance and writes a spec with a plan. `articulate voice check draft.md --intent spec.json` scores the draft against it and names, by line, the template shapes a line-by-line check misses: one-line paragraphs, anaphora runs, closing maxims, "It is not X. It is Y." See [a voice built from intent](docs/voice-intent.md).
- **Series review.** `articulate corpus` reads several documents together and reports repeated title formulas, shared paragraph scaffolds and even rhythm, with locations.
- **Dialogue.** `articulate dialogue` checks game and stage scripts and builds character voice sheets.

## Use it from anywhere

```bash
# command line
articulate check path/to/doc.md --gate
articulate check essay.md --profile essay --verbose
echo "some prose" | articulate score

# Python
python -c "import articulate; print(articulate.check_text('...', profile=articulate.profiles.load('research'))['gate'])"

# receipts
articulate receipt doc.md --profile research > doc.receipt.json
articulate verify doc.receipt.json doc.md        # exit 0 match, 1 drift, 2 unverifiable
articulate receipt doc.md --redact drop > receipts/doc.json   # keeps no matched text

# CI: SARIF for GitHub Code Scanning, Azure or reviewdog
articulate check docs/*.md --sarif > articulate.sarif

# editors and AI clients
python -m articulate.lsp_server     # LSP over stdio
python -m articulate.mcp_server     # MCP server
```

Every command also runs as `python -m articulate.cli`. The [CLI reference](docs/cli.md) lists each command, flag and exit code.

### Editor setup

The LSP server speaks standard LSP over stdio. A minimal Neovim registration:

```lua
vim.lsp.start({ name = "articulate", cmd = { "python", "-m", "articulate.lsp_server" },
  filetypes = { "markdown", "text", "tex" } })
```

In VS Code, any `LanguageClient` that launches the same command works.

### Editing with a model

In an MCP host, `fix`, `judge` and `polish` use sampling when the client offers it. Otherwise they return an edit plan: the host writes the rewrite with its own model and calls `edit_submit`, and Articulate checks protected spans and returns the accepted text. No second model account is needed.

```bash
articulate plan notes.md --goal fix > plan.json
articulate submit notes.md rewrite.md --plan PLAN_ID --model HOST_MODEL
articulate fix notes.md --backend none --out edited.md
articulate polish notes.md --backend ollama --json
```

From the command line, `--backend auto` tries a configured Anthropic key, the Claude CLI, OpenAI-compatible endpoints, Ollama and mechanical editing, in that order. See the [backend configuration](docs/cli.md#backend-configuration). A rewrite can change meaning, so read each one before you accept it.

On a `.tex` file the editor masks every math span before a rewrite and restores it byte for byte. The proof mode `academic/prove` routes to `judge` by default and rewrites only with `--fix`. Articulate checks the prose of a proof and leaves the mathematics alone.

### Where text goes

The checker and `--backend none` make no network call. The Anthropic and Claude CLI backends send text to Anthropic. An OpenAI-compatible endpoint or an Ollama server receives text at the address you configure. In an MCP host, edits go through that host and its model. Set `ARTICULATE_LOCAL_ONLY=1` to allow only loopback Ollama and mechanical editing.

A receipt made with `--redact drop` keeps the rule, tier and line of each finding and no matched text. `--redact hash` keeps a sha256 of the match, which can be reversed for rules with a small fixed word list. A voice profile holds aggregate statistics and stays on your computer until `articulate voice delete --all`.

## How it compares

- **Vale** enforces a style guide you write as YAML rules. Articulate ships its own rule set and register profiles, plus receipts and a texture score.
- **proselint** and **write-good** flag usage problems and weak phrasing. Articulate covers hedges and weak phrasing too, and adds contrast framing, rule-of-three lists and corporate verbs, with a profile deciding which ones block.
- **LanguageTool** and **Grammarly** check grammar and spelling, and their main products send text to a server. Articulate does not check grammar or spelling.
- **Hemingway Editor** scores readability in an editor window. Articulate runs from the command line and in CI, and names the rule and line for each finding.

## Install options

Version 0.19.1 is on PyPI as `articulate-writing`. The [changelog](CHANGELOG.md) lists what each release added.

- [Windows x64 native ZIP and MCPB packages](docs/native-local-package.md) bundle a Python runtime.
- The [Claude plugin](docs/claude-plugin.md) runs local checks and host editing in Claude Code, Codex and other MCP hosts that have Python installed.

## Documentation

- [Getting started](docs/getting-started.md): install, a first check and an editor squiggle.
- [Walkthrough](docs/walkthrough.md): one document from check to rewrite to a committed receipt.
- [Features](docs/features.md): every capability and how to reach it.
- [CLI reference](docs/cli.md): each command and flag, with exit codes.
- [What results mean](docs/boundaries.md): what a result and a receipt cover.
- [House voice](docs/house-voice.md), [series and your own voice](docs/series-and-voice.md), [a voice built from intent](docs/voice-intent.md), [dialogue](docs/dialogue.md).
- [Animated explainer](https://harperz9.github.io/repo-explainers/articulate.html): one draft through the checker, profiles, texture score and receipts.
