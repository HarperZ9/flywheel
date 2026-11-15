# Privacy Policy

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
