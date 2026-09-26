"""Capture hooks for Claude Code and Codex, run from the client's interpreter.

`python -m harness.capture_hooks <event> --client claude-code|codex` is the
mount. The package imports only the standard library and its own modules, so
a client can run it without Flywheel's dependencies loaded; a test enforces
that. The design and its limits are in docs/WRAPPER-HOOKS.md.
"""
