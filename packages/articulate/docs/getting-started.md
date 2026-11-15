# Getting started

Articulate reads prose and tells you where it uses a named writing device or
breaks a plain-writing standard, with a line number for each finding. It reads
style, and it flags most human writing too, so authorship is a question it leaves
open. The detector runs on your machine and works offline. Model editing follows the selected backend's
privacy policy. Install the package, run a check, create a receipt and connect
your editor with the commands below.

## Install

Version 0.19.1 is prepared for release. Its Windows x64 native ZIP and binary MCPB
packages include a Python runtime; see the [native package guide](native-local-package.md).
They include no model. A connected client supplies rewritten text through
`edit_plan` and `edit_submit`, using its own model account and permissions.

The Python package and source plugin need Python 3.9 or newer and the standard
library. The following commands select 0.19.1 after publication.

From PyPI:

```bash
pip install articulate-writing==0.19.1
```

From source:

```bash
git clone --branch v0.19.1 https://github.com/HarperZ9/articulate
cd articulate
pip install -e .
```

Three console commands are installed: `articulate` (the CLI), `articulate-lsp`
(the language server) and `articulate-mcp` (the stdio MCP server). They work from
a bare install. The optional FastMCP surface, `python -m articulate.mcp_server`,
uses the `mcp` extra:

```bash
pip install "articulate-writing[mcp]==0.19.1"
```

## Your first check

Point it at a Markdown or text file:

```bash
articulate check notes.md
```

You get a one-line verdict per file, then a line for each finding:

```
[articulate] notes.md [flavored]: 2 high, 1 medium (blocked)  texture 41/100
  L3 [HIGH antithesis] not X but Y: This is not a tool, but a force.
  L7 [HIGH em-dash] em-dash: a clause break using an em dash.
  L9 [MEDIUM register-word] AI-register vocabulary: we leverage synergy here.
```

Read it this way:

- The verdict is `clean`, `flagged`, or `unverifiable`. A `flagged` verdict means
  a HIGH or MEDIUM finding is present. An `unverifiable` verdict means the text is
  under the 30-word floor, where there are too few words to call it clean.
- Each finding carries a tier. HIGH marks the banned devices and named register
  words. MEDIUM marks strong frontier-model tells. LOW is an advisory that can fire
  on innocent prose, so it reports without blocking and expands with `--verbose`.
- The texture score is a graded 0 to 100 read of machine texture. It is a signal
  beside the verdict; the gate alone decides clean or flagged.

## Gate a commit or a build

`--gate` sets the exit code, so a checker can block a change:

```bash
articulate check docs/*.md --gate
```

The command exits 1 when any file is blocked under its profile, and 0 otherwise.
A profile decides which tiers block. The default profile blocks HIGH only; an
essay or a procedure profile blocks HIGH and MEDIUM. See
[Features](features.md#register-profiles) for the profile list.

## Your first receipt

A receipt is a re-derivable record of a verdict. Anyone with the same text and
the same ruleset recomputes the same findings on their own machine:

```bash
articulate receipt notes.md > notes.receipt.json
articulate verify notes.receipt.json notes.md
```

```text
[articulate] Match: re-derived 1 findings, gate ok, texture 0
```

`verify` prints one of three words and sets the exit code:

- `Match` (exit 0): the same text under the same ruleset re-derives identically.
- `Drift` (exit 1): the re-derived findings differ from the receipt.
- `Unverifiable` (exit 2): the ruleset moved, the text hash mismatches, or the
  text is below the signal floor, so the replay abstains.

## An editor squiggle

The language server speaks standard LSP over stdio, so any LSP client drives it.
A minimal Neovim registration:

```lua
vim.lsp.start({ name = "articulate", cmd = { "articulate-lsp" },
  filetypes = { "markdown", "text", "tex" } })
```

For VS Code, a thin client that launches the same command is in
`editors/vscode/`. See [Features](features.md#surfaces) for every surface.

## From an MCP host

`articulate-mcp` serves the tools over stdio from a bare install. Register it
in your host's MCP configuration:

```json
{
  "mcpServers": {
    "articulate": { "command": "articulate-mcp" }
  }
}
```

Ask the host to call `fix`, `judge` or `polish`. If the client advertised MCP
sampling, Articulate can request the host's model. Otherwise it returns a plan:
the calling model follows its instructions and calls `edit_submit` with the
original text, rewrite and plan ID. Articulate checks protected spans, retains
refused spans and returns the accepted text with a gate and host receipt. The
same pair is available directly as `edit_plan` and `edit_submit`.

This path needs no second model account. The host can still send text to a
remote model under its own policy. Plans and edit results contain source text;
keep them private when the source is private.

## Edit offline

Mechanical editing runs offline on your machine:

```bash
articulate fix notes.md --backend none --out edited.md
articulate judge notes.md --backend none --json
```

The deterministic backend fixes conservative mechanical cases, such as clause
dashes and doubled spaces, and reports the remaining findings. Quality scores
come from a model backend, and accuracy is for you to check. Inspect the gate
and refusal list before accepting it.

## Use an installed local model

With Ollama running and a model already installed:

```bash
articulate fix notes.md --backend ollama --out edited.md
```

Set `ARTICULATE_LOCAL_MODEL` to choose among the models you have pulled. Set
`ARTICULATE_LOCAL_ONLY=1` to keep editor selection on loopback Ollama and
deterministic editing; host and hosted editor paths are refused before a
connection. A document already in a host's conversation follows that host's
policy.

The CLI also supports Anthropic, the Claude CLI and OpenAI-compatible endpoints.
Automatic selection records unavailable backends and continues to a usable path,
ending with deterministic editing. See the [backend configuration reference](cli.md#backend-configuration)
for selection order, credentials and privacy.

## The house voice and your own voice

The house voice is opt-in. Turn it on, see what the model receives, and turn it
off or tune it:

```bash
articulate house on
articulate house show
articulate house off
articulate house set length=terse
```

Pipe model output through it with `articulate house apply -`. To build a
profile from your own writing and compare a draft with it:

```bash
articulate voice learn my-essays/*.md --name mine --mine
articulate voice compare draft.md --name mine
```

The [house voice spec](house-voice.md) and
[series review and your own voice](series-and-voice.md) cover both in full.

## Where to next

- [Walkthrough](walkthrough.md): a full pass over a real document, from screening
  to a rewrite to a committed audit record.
- [Features](features.md): every capability, what it gives you, and how to reach it.
- [CLI reference](cli.md): each command and flag.
- [Boundaries](boundaries.md): what a verdict and a receipt mean. Read this
  before you rely on a receipt for anything.
