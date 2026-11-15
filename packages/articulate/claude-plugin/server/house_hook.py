# -*- coding: utf-8 -*-
"""Run the Articulate house-voice hook from the source this plugin carries.

Claude Code runs this file when a session starts, resumes, clears or compacts,
and when the model finishes a reply, as

    python3 -I -S -B -X utf8 ${CLAUDE_PLUGIN_ROOT}/server/house_hook.py

The flags match server/serve.py: no PYTHONPATH, no site-packages, no bytecode
written into the plugin folder, UTF-8 streams. At session start it prints the
house-voice brief as additional context. At the end of a reply it says nothing
unless the user chose mode revise. It reads the packaged spec and the house
settings file, writes only its answer to stdout, starts no program, opens no
network connection and always exits 0. ARTICULATE_HOUSE_VOICE=off turns it off.

This file uses only syntax that old Python versions can parse.
"""
import os
import sys

if sys.version_info < (3, 9):
    sys.stderr.write("Articulate house hook needs Python 3.9 or later; skipping.\n")
    sys.exit(0)

SOURCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

if not os.path.isfile(os.path.join(SOURCE, "articulate", "house_hook.py")):
    sys.stderr.write("Articulate house hook: the bundled source is missing from this plugin "
                     "folder. Reinstall the plugin.\n")
    sys.exit(0)

sys.path.insert(0, SOURCE)

# The package initializer imports the style rules, which cost more than the
# brief itself. The hook's modules need none of the initializer, so the package
# is registered here by path and each module loads on first import. The Stop
# path imports the style rules itself, and only in mode revise.
import types  # noqa: E402

_package = types.ModuleType("articulate")
_package.__path__ = [os.path.join(SOURCE, "articulate")]
_package.__file__ = os.path.join(SOURCE, "articulate", "__init__.py")
sys.modules["articulate"] = _package

from articulate.house_hook import main  # noqa: E402  (the path is set just above)

sys.exit(main())
