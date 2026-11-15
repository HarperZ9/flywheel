# Articulate for VS Code

Inline writing-quality and writing-device diagnostics, powered by the Articulate
language server. The server runs locally with no network call; this extension is
a thin client that launches it.

## Requirements

The `articulate` Python package must be importable by the interpreter in
`articulate.pythonPath` (default `python`):

```bash
pip install articulate-writing   # or: pip install -e /path/to/articulate
```

## Settings

- `articulate.enable`: turn the server on or off.
- `articulate.pythonPath`: the Python interpreter that has `articulate`.
- `articulate.profile`: force a register profile (e.g. `essay`, `research`,
  `procedure`). Empty auto-detects from the file path or a `writing-profile:` tag.

## Build

```bash
npm install
npm run compile      # tsc -> out/extension.js
npx vsce package     # optional: produce a .vsix
```

Diagnostics map HIGH findings to warnings, MEDIUM to information, and LOW advisories
to hints, each carrying its rule id.
