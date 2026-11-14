"""gateway_key_cli.py -- `flywheel gateway-key`: local keys for tools behind the gateway.

  flywheel gateway-key create NAME [--token-limit N] [--models a,b,c]
                                   [--spend-limit USD --price-in USD --price-out USD]
                                        mint a key; it is printed once
  flywheel gateway-key list             every key, its limits and totals
  flywheel gateway-key show NAME        one key in full
  flywheel gateway-key revoke NAME      stop a key; its totals are kept
  flywheel gateway-key reset NAME       zero a key's running totals

A key opens the gateway's model interfaces (/v1/messages, /v1/responses) and
no other route. Prices are USD per million tokens and are yours to set; no
price table ships. The key itself goes to the system credential store.
Nothing here prints a key or any part of one after `create`.
"""
from __future__ import annotations

import argparse
import os
import sys

from harness import gateway_keys

USAGE = __doc__.split("\n\n", 1)[1].rstrip()


def _keys(environ=None, store=None) -> gateway_keys.Keys:
    from harness.lane_workdir import flywheel_home
    return gateway_keys.Keys(flywheel_home(os.environ if environ is None else environ),
                             store=store)


def _limits(row: dict) -> str:
    parts = []
    if row.get("token_limit") is not None:
        parts.append(f"{row['totals']['tokens']} of {row['token_limit']} tokens")
    else:
        parts.append(f"{row['totals']['tokens']} tokens, no token limit")
    spent = gateway_keys.spend(row)
    if row.get("spend_limit") is not None:
        parts.append(f"${spent:.6f} of ${row['spend_limit']:.6f}")
    elif spent is not None:
        parts.append(f"${spent:.6f}, no spend limit")
    return "; ".join(parts)


def render_list(rows: dict) -> str:
    if not rows:
        return "no gateway keys. Mint one with `flywheel gateway-key create NAME`."
    lines = []
    for name, row in sorted(rows.items()):
        state = "revoked" if row.get("revoked") else "live"
        lines.append(f"  {name:<20} {state:<8} {row['fingerprint']}  {_limits(row)}  "
                     f"calls {row['totals']['calls']}")
    return "\n".join(lines)


def _or(value, missing: str):
    return missing if value is None else value


def render_show(name: str, row: dict) -> str:
    shown, totals = gateway_keys.view(name, row), row["totals"]
    lines = [f"name          {name}",
             f"state         {'revoked' if row.get('revoked') else 'live'}",
             f"fingerprint   {row['fingerprint']} (first 16 hex of the key's SHA-256)",
             f"created       {row.get('created')} (Unix seconds)",
             f"models        {', '.join(row['models']) or 'any'}",
             f"token limit   {_or(row.get('token_limit'), 'none')}",
             f"spend limit   {_or(row.get('spend_limit'), 'none')} USD",
             f"prices        in {row.get('price_in')}, out {row.get('price_out')} "
             "(USD per million tokens)",
             f"calls         {totals['calls']} ({totals['estimated_calls']} charged by estimate)",
             f"tokens        {totals['tokens']} = input {totals['input_tokens']} + output "
             f"{totals['output_tokens']} + cache read {totals['cache_read_tokens']} + cache "
             f"write {totals['cache_write_tokens']} ({totals['estimated_tokens']} estimated)",
             f"spend         {_or(shown['spend_usd'], 'no prices set')} USD"]
    for what, left in shown["remaining"].items():
        lines.append(f"remaining     {left} {what}")
    return "\n".join(lines)


def _created(name: str, raw: str) -> str:
    return "\n".join([
        f"gateway key '{name}' created. This is the only time it is shown:",
        "",
        f"  {raw}",
        "",
        "Give it to the tool as its API key, with the gateway as the base URL:",
        "  Claude Code      ANTHROPIC_BASE_URL=http://127.0.0.1:8799  ANTHROPIC_AUTH_TOKEN=<key>",
        "  anthropic SDK    Anthropic(base_url=\"http://127.0.0.1:8799\", api_key=\"<key>\")",
        "  openai SDK       OpenAI(base_url=\"http://127.0.0.1:8799/v1\", api_key=\"<key>\")",
        f"Stop it with `flywheel gateway-key revoke {name}`."])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flywheel gateway-key", description=USAGE,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    verbs = parser.add_subparsers(dest="verb")
    create = verbs.add_parser("create", help="mint a key; it is printed once")
    create.add_argument("name")
    create.add_argument("--token-limit", type=int, default=None,
                        help="refuse calls once this many tokens are used")
    create.add_argument("--spend-limit", type=float, default=None,
                        help="refuse calls once this many USD are spent (needs both prices)")
    create.add_argument("--price-in", type=float, default=None,
                        help="USD per million input tokens, cached input included")
    create.add_argument("--price-out", type=float, default=None,
                        help="USD per million output tokens")
    create.add_argument("--models", default="",
                        help="comma-separated model names the key may send; default any")
    verbs.add_parser("list", help="every key, its limits and totals")
    for verb, text in (("show", "one key in full"), ("revoke", "stop a key"),
                       ("reset", "zero a key's running totals")):
        verbs.add_parser(verb, help=text).add_argument("name")
    return parser


def main(argv: "list[str] | None" = None, *, store=None, environ=None) -> int:
    parser = _parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.verb is None:
        parser.print_help()
        return 2
    try:
        keys = _keys(environ, store)
        if args.verb == "create":
            raw, _row = keys.create(
                args.name, token_limit=args.token_limit, spend_limit=args.spend_limit,
                price_in=args.price_in, price_out=args.price_out,
                models=args.models.split(","))
            print(_created(args.name, raw))
        elif args.verb == "list":
            print(render_list(keys.rows()))
        elif args.verb == "show":
            print(render_show(args.name, keys.row(args.name)))
        elif args.verb == "revoke":
            keys.revoke(args.name)
            print(f"gateway key '{args.name}' is revoked; its stored key was deleted and "
                  "its totals are kept")
        else:
            keys.reset(args.name)
            print(f"the totals of gateway key '{args.name}' are zero")
    except gateway_keys.KeysError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
