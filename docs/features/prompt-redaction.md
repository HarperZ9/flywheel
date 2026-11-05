# Prompt redaction: identifiers out before a hosted model reads them

A hosted model reads the full text of every prompt and tool result. The home
folder in a path, the login name, the machine name, an email address and a key
pasted from a terminal all ride along unless something takes them out first.
`harness.prompt_redact` swaps each for a stable placeholder, so the model can
still follow the structure of the text.

| Found | Becomes |
|---|---|
| the home folder, either separator, and any other user folder | `~` |
| the login name, as a whole word | `USER` |
| the machine name, as a whole word | `HOST` |
| an email address | `EMAIL-1`, `EMAIL-2`, ... (same address, same number) |
| a deny-list match | `ID-1`, `ID-2`, ... |
| a credential from the `trace_redact` catalog | `[REDACTED:<rule>:<tag>]` |

Addresses at `example.com`, `.test`, `.invalid` and noreply addresses stay. The
report counts each category and never prints a matched value.

## Use it

As a filter in front of any script that sends text to a hosted API:

```
python -m harness.prompt_redact filter < notes.txt > notes.redacted.txt
```

As a Claude Code `UserPromptSubmit` hook, in a settings file you control:

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [
  {"type": "command", "command": "python -m harness.prompt_redact hook"}]}]}}
```

A prompt with no finding passes untouched. A prompt with a finding is blocked
before it is sent, and the block reason shows the redacted copy to resubmit. The
model never sees the reason. A `UserPromptSubmit` hook can block a prompt or add
context to it; it cannot rewrite it, so a block is the one way to keep the
original text out of the request.

## The deny list

Serials, account IDs, a partner's name: anything private goes in an untracked
file of regexes, one per line, `#` for comments. The same format serves the
publish metadata check. The filter reads `--deny-list FILE`, then
`FLYWHEEL_REDACT_DENYLIST`, then `PUBLISH_DENYLIST`, then
`~/.flywheel/redact-denylist.txt`. A named file that is missing is an error,
so a typo in the path never runs the filter without the list.

## Limits

- Tool results are not covered yet. Whether a `PostToolUse` hook can replace a
  built-in tool's output in the current Claude Code release is unchecked; a
  `PreToolUse` rule that blocks reads of marked files is the planned next step.
- Placeholders are stable within one call. Two prompts can number the same
  address differently.
- Patterns are regexes. A name spelled in a form no rule names, or split across
  lines, passes. A task that needs a redacted value fails, and the block says
  which categories it found.
- The account, the IP address and the content the task needs still reach the
  provider. This filter shrinks what rides along; it does not make a session
  anonymous.
