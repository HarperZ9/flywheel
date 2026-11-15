# Articulate Writing

Articulate Writing checks prose on your computer before you ship it. It names
writing patterns such as filler openers, stacked hedges and unsupported
superlatives, shows the line and the words where each one occurs, and gives the
label explaining each pattern. Use it on documentation, READMEs, release notes,
commit messages and drafts. The checker runs on your computer and sends the text
nowhere; the calling model reads the text as part of your conversation.

It can also give the model in your client a voice of its own, the Articulate
house voice, from the first reply of every session. It is off until you turn
it on: set `ARTICULATE_HOUSE_VOICE=on` in the environment Claude Code starts
from. It is openly a model's voice: answer first, numbers with their
denominators, "I" only for what it did in the session, no praise openers, no
offers to help further, no em dashes. It never claims a human life.
`ARTICULATE_HOUSE_VOICE=off`, or leaving the variable unset, keeps it off. The
`articulate house on` and `articulate house off` commands do the same through a
settings file; the `articulate` command line comes with the PyPI package
`articulate-writing`, which this plugin does not install. The published spec is
[docs/house-voice.md](https://github.com/HarperZ9/articulate/blob/release/0.5.x/docs/house-voice.md).

## What you get

- The house voice, once you turn it on. At session start (and after a resume,
  clear or compaction) a hook hands the model the house-voice brief, about 1,500 characters, with
  its version and fingerprint. `house_brief` returns the brief, and
  `house_transform` applies the house voice's closed list of exact edits to
  model output you pass it, with a meaning guard and a receipt. Mode `revise`
  (`ARTICULATE_HOUSE_VOICE=revise`, or `articulate house set mode=revise` with
  the separate command line) adds a Stop hook check: after each reply, the hook
  reads the reply's text and, when it claims a human life or breaks a banned
  rule, asks for one revision. It costs a model turn, so it is off by default.
- Series review: `corpus_check` reads several documents as one series and
  names repeated title formulas, shared phrases, paragraph scaffolds, even
  rhythm and missing perspective, with locations. `title_workshop`,
  `interview` and `restructure_plan` group titles, ask the author questions
  and propose moving limit lines. They never write first-person text for the
  author.
- Your own voice, when you build one: `voice_compare` places a draft against a
  voice profile you made on this computer with `articulate voice learn --mine`,
  and `voice_apply_plan` plans an edit of your own draft toward that voice,
  only when you say the draft is yours. No tool learns, exports or deletes a
  profile. The separate `articulate` command line (PyPI package
  `articulate-writing`, not installed by this plugin) does that.
- Dialogue and character voice: `dialogue_check` reads a script you pass it
  (LWD lines, `NAME: text` lines or a printed play) and reports epigram shapes,
  antithesis, theme statements and closing zingers in the spoken lines, checks
  each line against the character voice sheets you pass, and scores how well a
  plain classifier can tell the characters apart. It opens no file.

- `check` returns each HIGH and MEDIUM finding with its rule, tier, line, span
  and label, a count of LOW advisories (`advisory_count`), `clean` and `verdict`
  (`clean` or `flagged`), a heuristic `texture_score` and cadence statistics. A
  long document returns the first 50 span records by default and never more
  than about 30,000 characters of them; the verdict and counts cover the full check;
  `hits_omitted` reports omitted span records.
- `score` returns the heuristic 0-100 `texture_score`, `hard_hits`, `advisories`,
  word count, passive-voice and adverb rates, and a uniform-cadence flag.
- `edit_plan` prepares findings, protected spans, `masked_text`, editing
  instructions and a `plan_id` for the calling model. `edit_submit` takes the
  original text, the model's masked rewrite and that token, restores masks,
  guards protected spans and returns accepted text with a host receipt.
- `fix`, `judge` and `polish` run offline in the plugin: `auto` or `host` returns
  a host plan, and `none` runs deterministic checks or edits. Explicit network,
  subprocess and sampling backends are refused before execution.
- An edit-time hook runs after the model writes or edits a prose file
  (`.md`, `.mdx`, `.markdown`, `.txt`, `.rst`, `.adoc`, `.tex`). When the edit
  carries the text before and after, it names numbers, links, quotes,
  citations, modals, scope words, negations and names that the edit dropped,
  added or changed. It also lists style findings in the new text, leaving out
  words inside quotation marks and block quotes, which belong to the person
  quoted (`ARTICULATE_EDIT_HOOK_QUOTES=check` checks them too). The model
  gets this as context on its next step. The hook never blocks an edit, and
  `ARTICULATE_EDIT_HOOK=off` turns it off. Codex runs a plugin hook only after
  you review and trust it.
- `articulate.status` reports the server version, and `articulate.doctor`
  reports a setup summary you can paste into an issue.
- The `prose-review` skill tells the calling model when to run the checks, how to report
  them, and to propose an edit only where you want one. The `prose-edit` skill
  uses the host-edit protocol, with a check-only fallback.

## Requirements

- A local Claude Code or Codex host. The server has automated Windows and Linux test coverage. Cowork
  also loads plugins, and this plugin has not been tested there. Chat on
  claude.ai loads the skill and does not start the local checker.
- Python 3.9 or later, runnable as `python3`. Nothing else to install: the
  plugin carries its own copy of the checker, which uses only the Python
  standard library.

## Install

Install Articulate Writing from the Claude plugin directory, or add this
repository's `claude-plugin` folder as a marketplace. The folder carries its own
copy of the checker, so there is nothing else to install:

```bash
claude plugin marketplace add ./claude-plugin
claude plugin install articulate-writing@articulate-writing
```

Run the first command from a checkout of this repository on the
`release/0.5.x` branch. To build a separate plugin repository for local
development, follow
[the build guide](https://github.com/HarperZ9/articulate/blob/release/0.5.x/docs/claude-plugin.md).

The same release also prepares Windows x64 native ZIP and binary MCPB packages
with a Python runtime included. See the
[native package guide](https://github.com/HarperZ9/articulate/blob/release/0.5.x/docs/native-local-package.md).
Those packages are separate from this source plugin. Both forms include no model
and use the calling model for host edits. Native client installation and
marketplace acceptance remain unverified.

Restart Claude Code, then run `/mcp`. The `articulate` server shows as
connected.

For Codex, add the built folder through a repo or personal marketplace as
[the build guide](https://github.com/HarperZ9/articulate/blob/release/0.5.x/docs/claude-plugin.md)
shows. Portable hosts read `plugin.json` and `mcp.json`; older Codex hosts use
the compatibility manifest. Client installation still needs a local Python
process. This does not provide a checker in an ordinary web chat.

## Try it

- "Check the prose in docs/guide.md and explain each finding with its
  label."
- "Score this release note and report the structural rates." (Paste the
  note after the request.)
- "Review my commit message draft for filler and hedging, and suggest edits only
  for the blocking findings." (Paste the draft after the request.)

## What it runs

| What | Detail |
|:-|:-|
| Processes | The server: `python3 -I -S -B -X utf8` running the plugin's `server/serve.py`. Claude Code starts it with the session and stops it at the end. The hooks: the same command running `server/house_hook.py` at session start and at the end of each reply (the end-of-reply event holds Claude's last reply, which the hook reads only in mode `revise`), and `server/edit_hook.py` after each file write or edit. Each exits when it has answered. All run the first `python3` on your PATH, which is a virtual environment's Python when you have one activated. |
| Files | It loads its own source from the plugin folder and the Python standard library, and no installed package: `-S` skips every site-packages folder. It writes no file: no log, no cache, no bytecode. It reads two more things, and only reads them: the house-voice settings file (`house.json` in your Articulate config folder) when the house hooks and tools run, and, for `voice_compare`, `voice_apply_plan` and `interview` with a voice name, one profile and `identity.json` from your local voice store. The edit hook reads the edit from the event the host sends on standard input and does not open the edited file. |
| Network | None. It opens no connection. |
| Other programs | None. |
| Settings | It sets `ARTICULATE_MCP_TOOLS=local` and `ARTICULATE_LOCAL_ONLY=1` for its own process and changes no host setting. |

The package supports optional external editing backends outside this plugin.
The plugin settings restrict editor tools to host plans and deterministic work.
A host plan asks the model already in your conversation to write the rewrite;
the plugin does not call another model.

## Privacy Policy

Last updated: 2026-10-02. This policy covers the Articulate Writing plugin for
local Claude Code and Codex hosts. It is also published at
https://github.com/HarperZ9/articulate/blob/release/0.5.x/claude-plugin/PRIVACY.md.

### What this plugin runs and handles

**Hooks.** The plugin has three hooks. Each runs `python3 -I -S -B -X utf8` on a file in `${CLAUDE_PLUGIN_ROOT}/server/`, answers once on standard output and exits. No hook opens a network connection, starts a program or writes a file.

- **SessionStart** runs `house_hook.py` when a session starts, resumes, is cleared or is compacted, for up to 10 seconds. When you have turned the house voice on, it adds the published house-voice brief to Claude's context. The brief comes from the spec packaged in the plugin and your tuning keys. It is the same text for everyone with the same keys and holds nothing about you. With the house voice off, which is the default, it prints nothing.
- **Stop** runs `house_hook.py` after every reply Claude finishes, for up to 15 seconds. Claude Code's Stop event holds the full text of Claude's last reply. The Stop hook is opt-in: it reads that reply text only when you set the house voice to mode `revise` (for example `ARTICULATE_HOUSE_VOICE=revise`). In that mode, if the reply claims a human life or breaks a banned style rule, the hook returns a block decision that asks Claude to revise the reply once and names each finding by line. When Claude Code marks the event as already continued by a Stop hook, the hook says nothing, so it forces at most one revision per reply. In every other mode it ignores the reply text and prints nothing. It never blocks a tool call.
- **PostToolUse** runs `edit_hook.py` after Claude writes or edits a file (Write, Edit, MultiEdit and apply_patch), for up to 15 seconds. The hook reads the edit event, which holds the file name and the text before and after the edit. For prose files (.md, .txt, .rst, .tex and similar) it returns advice about changed meaning and style to Claude. It opens no file and never blocks the edit.

Claude Code's events also carry the session ID, the path of the conversation transcript and the working folder. The hooks ignore them and never open the transcript.

**MCP server.** The plugin starts one local MCP server named `articulate` with `python3 -I -S -B -X utf8 ${CLAUDE_PLUGIN_ROOT}/server/serve.py`. `${CLAUDE_PLUGIN_ROOT}` is the folder where Claude Code installed the plugin. The launch sets two environment values: `ARTICULATE_MCP_TOOLS=local` and `ARTICULATE_LOCAL_ONLY=1`. The server talks to Claude Code over standard input and output only. Every tool is read-only.

**Network.** With those two values, every tool runs on your computer. The server opens no network connection and sends nothing to the author or to any other service. Claude still reads the text as part of your conversation, and your Claude provider handles that conversation.

**Code left out.** The Articulate command line tool also has optional model backends that read provider API keys and call a model provider, a local Ollama server or the `claude` program. This plugin does not include them: the folder carries only the modules its local tools and hooks import. If someone changes the plugin's launch values to ask for a model backend, the tool answers that this build does not include one.

**Files it reads.** Its own folder. The house settings file `articulate/house.json` in `%APPDATA%` on Windows or `$XDG_CONFIG_HOME` (default `~/.config`) elsewhere, or in `ARTICULATE_CONFIG_DIR` when set. The hooks and the house tools read it. Only when you name a voice in `voice_compare`, `voice_apply_plan` or `interview`, that one profile and `identity.json` from the voice store in `%LOCALAPPDATA%\articulate\voice` on Windows or `$XDG_DATA_HOME/articulate/voice` (default `~/.local/share/articulate/voice`) elsewhere, or in `ARTICULATE_VOICE_DIR` when set. No other file.

**Files it writes.** None. Only the separate Articulate command line writes the settings file and the voice store, and this plugin does not include that command line. The `-B` flag keeps Python from writing bytecode into the plugin folder.

**Environment variables and credentials.** The server reads `ARTICULATE_MCP_TOOLS` and `ARTICULATE_LOCAL_ONLY`, which the plugin sets itself. The hooks and tools read `ARTICULATE_HOUSE_VOICE` (`off`, `on`, `brief`, `default` or `revise`), the tuning keys `ARTICULATE_HOUSE_LENGTH`, `ARTICULATE_HOUSE_END_LINE`, `ARTICULATE_HOUSE_HEADINGS`, `ARTICULATE_HOUSE_LISTS`, `ARTICULATE_HOUSE_LIMITS` and `ARTICULATE_HOUSE_FIRST_PERSON`, `ARTICULATE_CONFIG_DIR` with `APPDATA` or `XDG_CONFIG_HOME`, and `ARTICULATE_VOICE_DIR` with `LOCALAPPDATA` or `XDG_DATA_HOME`. The edit hook reads `ARTICULATE_EDIT_HOOK`; set it to `off` to turn that hook off. It also reads `ARTICULATE_EDIT_HOOK_QUOTES`; set it to `check` to check quoted words. Python reads your home folder location when a folder variable is unset. None of these is a credential, and the plugin reads no credential. The `-I` flag also makes Python ignore its own `PYTHON*` variables.

**Data collected.** The plugin reads the text the calling host passes to one of its tools, the events the host passes to its hooks (a session start, a file edit, and the end of a reply, which holds Claude's last reply), its own house-voice spec, and your house-voice settings file. When you name a voice profile in `voice_compare`, `voice_apply_plan` or `interview`, it reads that one profile and the store's `identity.json` from the local voice store. It does not open your other files, the conversation transcript or saved memory. The Stop hook receives Claude's last reply in its event and reads it only in mode `revise`. It collects no account details, usage statistics or telemetry.

**Use and storage.** The plugin checks text, applies the house voice and
prepares or validates host edits in memory on your computer, then returns the
result to the host. It writes no log, cache or copy of the text to disk. When
you turn the house voice on, it adds the house-voice brief to the model's
context at session start; the brief is the same published text for everyone
and holds nothing about you. A voice
profile is made only by the separate Articulate command line
(`articulate voice learn --mine`), which this plugin does not include, from
files you name. It holds measured aggregates, never a sentence of your
samples, stays on your computer, and `articulate voice delete --all` removes
every profile, the identity file and the store folder. During
`voice_apply_plan` the profile's plain-sentence description enters the host
conversation, because the host model writes the rewrite.

**Third-party sharing.** The plugin opens no network connection and starts no
other program. The calling host already has the text in the conversation and
may send it to its model provider, together with the house-voice brief and,
during `voice_apply_plan`, your profile's description. That provider's privacy
policy and your account settings govern the conversation and tool results. No
second model account is needed by the plugin.

**Retention.** The plugin writes no persistent copy of the text, log or cache.
Request and response text can remain in process memory during the server session.
Voice profiles stay in your local voice store until you delete them. The host
may retain conversation text and tool results locally or remotely; its settings
and provider terms govern those copies.

**Contact.** Ask a question about this policy or the plugin at
https://github.com/HarperZ9/articulate/issues. Report a security problem
privately through the repository's security advisory reporting page.

**Changes.** A change to this policy ships in a new plugin version with a new
date above, and the changelog at
https://github.com/HarperZ9/articulate/blob/release/0.5.x/CHANGELOG.md lists it.

## Troubleshooting

**The `articulate` server shows as failed in `/mcp`.** Claude Code could not
start `python3`, or the Python it found is too old. Check with `python3
--version` in a terminal.

- Windows, "Python was not found" or a Microsoft Store window: install the
  Python install manager, which provides `python3`. The traditional python.org
  installer provides `python` and no `python3`. Restart Claude Code afterwards.
- macOS, a prompt to install the command line developer tools: accept it, or
  install Python from python.org or Homebrew. The plugin has not been tested on
  macOS yet.
- Linux: install the `python3` package with your distribution's package
  manager.
- "needs Python 3.9 or later": install a newer Python 3 and restart Claude
  Code.

**The tools are listed and a call fails.** Ask Claude to run the Articulate
doctor tool. It reports the plugin version, the Python version and which tools
are listed, with no file paths. Paste that report into an issue.

## Limits

- A protected-span guard and detector gate check words and protected spans
  only. Meaning, quality and factual correctness stay with you: inspect refused
  edits and review meaning.
- `texture_score` is a heuristic. It does not estimate the probability that a
  model wrote the text.
- The house-voice brief is an instruction. Host models follow it unevenly, and
  no hook can rewrite a model's reply after the model writes it. The deterministic
  transform covers only its closed list.
- Codex may not run plugin hooks. If the brief does not arrive in Codex, ask
  for the `house_brief` tool's output and paste the brief into AGENTS.md. The
  separate command line prints it ready for that file with
  `articulate house brief --agents`.
- The voice identity binding is a consent and provenance record. A local user
  who edits the JSON can defeat it, so it is not access control.

- The rules are written for English prose. Text in other languages gets few or
  no findings, and a clean result there says nothing about the writing.
- These findings name prose patterns and where they occur. They do not show who
  or what wrote the text, and no finding or count is a basis for an accusation.

## Support and license

Report a problem or ask a question at
https://github.com/HarperZ9/articulate/issues.

Articulate Writing is source-available under the Functional Source License 1.1
with the MIT future license (`FSL-1.1-MIT`): each release becomes available
under the MIT license on the second anniversary of its release. See `LICENSE`.
