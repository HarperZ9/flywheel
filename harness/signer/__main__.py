"""python -m harness.signer {init,serve,pubkey,rewind,hello,head}

Run ``init``, ``serve`` and ``rewind`` AS THE SIGNER IDENTITY. They read or
write the signer's home, which the agent's identity must not be able to read.
``pubkey`` reads only the public file. ``hello`` and ``head`` are client calls
any user may make; ``hello`` prints the key and the isolation the signer
measured for the caller. Setup for both platforms: docs/SEPARATE-SIGNER.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _ready(address: str):
    def ready():
        print(json.dumps({"ready": True, "address": address}), flush=True)
    return ready


def _cmd(args) -> int:
    from . import keys, server
    if args.cmd == "init":
        print(keys.create(Path(args.home)).hex())
        return 0
    if args.cmd == "pubkey":
        print((Path(args.home) / keys.PUBLIC_NAME).read_text(encoding="ascii").strip())
        return 0
    if args.cmd == "serve":
        server.serve(Path(args.home), args.address, ready=_ready(args.address))
        return 0
    if args.cmd == "rewind":
        from .journal import Journal
        out = Journal(Path(args.home)).rewind(args.store, server._now())
        print(json.dumps(out))
        return 0
    if args.cmd == "hello":
        from .client import SignerClient
        print(json.dumps(SignerClient(args.address, args.pubkey).hello()))
        return 0
    if args.cmd == "head":
        from .client import SignerClient
        print(json.dumps(SignerClient(args.address, args.pubkey).head(args.store)))
        return 0
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness.signer", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "pubkey", "serve", "rewind"):
        p = sub.add_parser(name)
        p.add_argument("--home", required=True, help="the signer's own home")
    sub.choices["serve"].add_argument("--address", required=True)
    sub.choices["rewind"].add_argument("--store", required=True)
    for name in ("hello", "head"):
        h = sub.add_parser(name)
        h.add_argument("--address", required=True)
        h.add_argument("--pubkey", default="", help="pinned public key, hex")
    sub.choices["head"].add_argument("--store", required=True)
    args = ap.parse_args(argv)
    try:
        return _cmd(args)
    except Exception as exc:  # noqa: BLE001 -- report, then exit nonzero
        print(f"signer: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
