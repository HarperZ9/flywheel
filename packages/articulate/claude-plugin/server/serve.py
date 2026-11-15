# -*- coding: utf-8 -*-
"""Start the Articulate MCP server from the source this plugin carries.

Claude Code runs this file as

    python3 -I -S -B -X utf8 ${CLAUDE_PLUGIN_ROOT}/server/serve.py

-I keeps Python from reading PYTHONPATH and the user site-packages folder, and
from putting the working folder on the module path. -S skips the site module, so
no site-packages folder is searched and no .pth file there runs: the server runs
on the standard library and this plugin's source, which the path insert below
puts first. -B keeps Python from writing bytecode into the plugin folder.
-X utf8 makes the standard streams UTF-8; the server also switches them itself.

The server reads JSON-RPC requests on stdin and writes responses on stdout. It
opens no network connection, starts no other program and writes no file.

This file uses only syntax that old Python versions can parse, so an interpreter
older than 3.9 prints the requirement instead of a syntax error.
"""
import os
import sys

REQUIRED = (3, 9)

if sys.version_info < REQUIRED:
    sys.stderr.write("Articulate Writing needs Python %d.%d or later; python3 here is "
                     "Python %d.%d. Install a newer Python 3 and restart Claude Code.\n"
                     % (REQUIRED + tuple(sys.version_info[:2])))
    sys.exit(1)

SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

if not os.path.isfile(os.path.join(SOURCE, "articulate", "local_mcp.py")):
    sys.stderr.write("Articulate Writing: the bundled source is missing from this plugin "
                     "folder. Reinstall the plugin.\n")
    sys.exit(1)

sys.path.insert(0, SOURCE)

from articulate.local_mcp import main  # noqa: E402  (the path is set just above)

sys.exit(main())
