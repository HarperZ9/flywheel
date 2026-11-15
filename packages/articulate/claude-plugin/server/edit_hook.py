# -*- coding: utf-8 -*-
"""Run the Articulate edit-time check from the source this plugin carries.

Claude Code and Codex run this file after the model writes or edits a file, as

    python3 -I -S -B -X utf8 ${CLAUDE_PLUGIN_ROOT}/server/edit_hook.py

The flags match server/serve.py: no PYTHONPATH, no site-packages, no bytecode
written into the plugin folder, UTF-8 streams. The check reads the hook event on
stdin and prints advisory context for prose files on stdout. It opens no file,
starts no program, opens no network connection and always exits 0, so it never
blocks an edit.

This file uses only syntax that old Python versions can parse.
"""
import os
import sys

if sys.version_info < (3, 9):
    sys.stderr.write("Articulate edit hook needs Python 3.9 or later; skipping.\n")
    sys.exit(0)

SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

if not os.path.isfile(os.path.join(SOURCE, "articulate", "edit_hook.py")):
    sys.stderr.write("Articulate edit hook: the bundled source is missing from this plugin "
                     "folder. Reinstall the plugin.\n")
    sys.exit(0)

sys.path.insert(0, SOURCE)

from articulate.edit_hook import main  # noqa: E402  (the path is set just above)

sys.exit(main())
