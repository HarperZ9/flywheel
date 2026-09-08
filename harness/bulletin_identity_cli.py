"""CLI for preparing and binding a native Bulletin signing identity."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from .bulletin_identity import (
    DEFAULT_BASE_URL,
    DEFAULT_HANDLE,
    BulletinIdentityError,
    error_body,
    prepare_identity,
)


def main(
        argv: list[str] | None = None, *,
        http_get_json: Callable[..., dict] | None = None,
        signed_post_json: Callable[[str, dict], dict] | None = None,
        credential_source: Callable[[str], str] | None = None,
        keychain_get: Callable[[str], str | None] | None = None,
        keychain_set: Callable[[str, str], dict] | None = None,
        token_hex: Callable[[int], str] | None = None,
        generate_key_json: Callable[[], str] | None = None,
        keychain_lock: Callable[[str], object] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(list(argv if argv is not None else sys.argv[1:]))
    try:
        if args.command == "prepare":
            result = prepare_identity(
                args.key,
                base_url=args.base,
                handle=args.handle,
                create=args.create,
                register=args.register,
                store_keychain=args.store_keychain,
                bind_owner=args.bind_owner,
                state_root=args.state_root,
                allow_loopback=args.allow_loopback,
                timeout=args.timeout,
                max_pow_bits=args.max_pow_bits,
                http_get_json=http_get_json,
                signed_post_json=signed_post_json,
                credential_source=credential_source,
                keychain_get=keychain_get,
                keychain_set=keychain_set,
                token_hex=token_hex,
                generate_key_json=generate_key_json,
                keychain_lock=keychain_lock,
                keychain_lock_root=args.state_root,
            )
        else:
            parser.error("unknown command")
            return 2
    except BulletinIdentityError as exc:
        print(json.dumps(error_body(exc.code), sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flywheel bulletin-identity",
        description="Prepare a Bulletin Ed25519 identity under native custody.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser(
        "prepare",
        help="validate a key file, check the board, and optionally store/register",
    )
    prepare.add_argument("--key",
                         help="optional path to import a local Bulletin Ed25519 JWK file")
    prepare.add_argument("--create", action="store_true",
                         help="create a new identity and store it directly in the OS keychain")
    prepare.add_argument("--base", default=DEFAULT_BASE_URL,
                         help="Bulletin base URL")
    prepare.add_argument("--handle", default=DEFAULT_HANDLE,
                         help="agent display handle, default: flywheel")
    prepare.add_argument("--register", action="store_true",
                         help="perform the signed /v1/agents registration if absent")
    prepare.add_argument("--store-keychain", action="store_true",
                         help="store the validated key in the OS keychain")
    prepare.add_argument("--bind-owner",
                         help="bind BULLETIN_AGENT_JWK to an owner-scoped credential handle")
    prepare.add_argument("--state-root", type=Path,
                         help="Flywheel state root for credential handles")
    prepare.add_argument("--allow-loopback", action="store_true",
                         help="allow an http://127.0.0.1 or localhost base URL for local tests")
    prepare.add_argument("--timeout", type=int, default=20,
                         help="HTTP timeout in seconds")
    prepare.add_argument("--max-pow-bits", type=int, default=24,
                         help="maximum proof-of-work difficulty this helper will attempt")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
