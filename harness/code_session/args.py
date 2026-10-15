"""args.py -- the `flywheel code` command line."""
from __future__ import annotations

import argparse
import os

from .backends import DEFAULT_MAX_TOKENS
from .policy import MODES
from .session import DEFAULT_MAX_STEPS

DESCRIPTION = "`flywheel code`: an interactive coding session in the current folder."


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="flywheel code", description=DESCRIPTION)
    ap.add_argument("-p", "--print", dest="prompt", default=None, metavar="REQUEST",
                    help="run one request, print the answer and exit; with no one to ask, "
                         "calls that would ask are refused, so pass --mode edit or auto")
    ap.add_argument("--root", default=".", help="project folder (default: current folder)")
    ap.add_argument("--mode", choices=MODES, default="ask",
                    help="permission mode (default: ask)")
    ap.add_argument("--backend", default="auto", help="pin a backend by name")
    ap.add_argument("--model", default="", help="model id for the chosen backend")
    ap.add_argument("--providers", default="",
                    help="comma list of hosted providers to consider (default: all with keys)")
    ap.add_argument("--local-only", action="store_true", help="never call a hosted provider")
    ap.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--test-cmd", default="", help="tests a turn must pass before it is done")
    ap.add_argument("--compact-budget", type=int, default=60000,
                    help="fold the conversation past about this many estimated tokens; 0 is off")
    ap.add_argument("--no-instructions", action="store_true",
                    help="do not read AGENTS.md, CLAUDE.md or FLYWHEEL.md")
    ap.add_argument("-c", "--continue", dest="cont", action="store_true",
                    help="resume the newest saved session for this folder")
    ap.add_argument("--resume", default="", metavar="ID", help="resume a saved session")
    ap.add_argument("--sessions", action="store_true",
                    help="list saved sessions for this folder and exit")
    ap.add_argument("--no-save", action="store_true", help="do not save this session")
    ap.add_argument("--no-mcp", action="store_true", help="start no MCP servers")
    ap.add_argument("--trust-project-mcp", action="store_true",
                    help="start the project's MCP servers without asking")
    ap.add_argument("--trust-project-hooks", action="store_true",
                    help="run the project's hooks without asking")
    ap.add_argument("--worktree", default="", metavar="NAME",
                    help="work in a git worktree on branch flywheel/NAME, carrying your "
                         "uncommitted changes; your checkout is not touched")
    ap.add_argument("--plain", action="store_true",
                    help="screen-reader friendly output: words, not symbols (also "
                         "FLYWHEEL_SCREEN_READER=1)")
    ap.add_argument("--acp", action="store_true",
                    help="serve the Agent Client Protocol on stdin and stdout for an editor")
    ap.add_argument("--output-format", choices=("text", "json", "stream-json"), default="text",
                    help="with -p: text, one JSON result, or one JSON object per event")
    args = ap.parse_args(argv)
    args.root = os.path.abspath(args.root)
    return args
