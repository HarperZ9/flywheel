"""Argument parsing for `python -m articulate.editor` (judge, fix, polish, review).

Split out of editor.py. It calls the editor functions through the module, so a
test that patches articulate.editor still steers the command line.
"""
import argparse
import os

from . import editor


def main():
    ap = argparse.ArgumentParser(description="Articulate editor layer (judge / fix).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--judge", metavar="FILE")
    g.add_argument("--fix", metavar="FILE")
    g.add_argument("--polish", metavar="FILE")
    g.add_argument("--review", metavar="FILE")
    ap.add_argument("--out", metavar="FILE", default=None)
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--bar", type=int, default=4, help="quality bar 1-5 for --polish")
    ap.add_argument("--mode", default=None,
                    help="a writing mode (domain/articulation, e.g. memo/argue)")
    ap.add_argument("--backend", default=None,
                    choices=("auto", "host", "sampling", "anthropic", "claude-cli", "openai", "ollama", "none"))
    args = ap.parse_args()

    target = args.judge or args.fix or args.polish or args.review
    if not os.path.isfile(target):
        print(f"[articulate] no such file: {target}")
        return 2
    from . import detector
    try:
        with open(target, "rb") as fh:
            head = fh.read(8192)
    except OSError as e:
        print(f"[articulate] cannot read {target}: {e}")
        return 2
    reason = detector.binary_reason(head, name=target)
    if reason:
        print(f"[articulate] cannot edit {target}: {reason}")
        return 2
    if args.judge:
        editor.judge(args.judge, args.mode, args.backend)
    elif args.review:
        editor.review(args.review, args.mode, args.backend)
    elif args.polish:
        return editor.polish(args.polish, args.out, max(1, args.passes),
                      max(1, min(5, args.bar)), mode=args.mode, backend=args.backend)
    else:
        return editor.fix(args.fix, args.out, max(1, args.passes), mode=args.mode, backend=args.backend)
    return 0
