# Flywheel for VS Code

Runs `flywheel code` in a VS Code terminal, in your workspace folder. Every
step the agent takes is checked against your permission mode and recorded on a
hash-chained ledger you can recheck; see the
[flywheel code guide](https://github.com/HarperZ9/flywheel/blob/main/docs/CODE-SESSION.md).

## Commands

- **Flywheel: Start a coding session** opens a session in the workspace folder.
- **Flywheel: Continue the last session** resumes the newest saved session.
- **Flywheel: Ask about this file** and **Ask about the selection** send your
  question with an `@file` mention, and the line range for a selection.
- **Flywheel: Check the install (doctor)** runs `flywheel doctor`.

## Settings

- `flywheel.command`: the command or its full path (default `flywheel`).
- `flywheel.mode`: `plan`, `ask` (default), `edit` or `auto`.
- `flywheel.extraArgs`: more arguments, for example `["--backend", "claude"]`.

Needs Flywheel 1.6.0 or newer on PATH (`python -m pip install flywheel-verify`).
The extension sends nothing anywhere; the session talks to the model you
configured in Flywheel.

## Limits

- A file whose path contains a space is named in the request but not attached,
  because `@` mentions end at a space.
- The extension is not on the Visual Studio Marketplace yet. Install the
  `.vsix` from a Flywheel release with `code --install-extension
  flywheel-code-<version>.vsix`, or build it with
  `python scripts/build_vscode_vsix.py`.
