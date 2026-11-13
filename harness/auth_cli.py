"""auth_cli.py -- `flywheel auth`: accounts and sign-in.

  flywheel auth list                    providers, account labels, which is active
  flywheel auth use PROVIDER LABEL      switch the active account
  flywheel auth remove PROVIDER LABEL   delete an account's stored key
  flywheel auth status                  sign-in state per provider
  flywheel auth login PROVIDER          browser or vendor-CLI sign-in
  flywheel auth logout PROVIDER         clear a sign-in token

Add an account with `flywheel setup --provider PROVIDER --account LABEL`.
Nothing here prints a key or any part of one.
"""
from __future__ import annotations

import sys

from harness import accounts

USAGE = __doc__.split("\n\n", 1)[1].rstrip()
_ACCOUNT_VERBS = ("list", "use", "remove")


def render_list(rows: list) -> str:
    """Labels only. The active one is starred; an environment variable that
    overrides the stored accounts is named."""
    lines = []
    for row in rows:
        if row["labels"]:
            shown = ", ".join(f"*{x}" if x == row["active"] else x for x in row["labels"])
        else:
            shown = "no stored account"
        line = f"  {row['provider']:<11} {shown}"
        if row["labels"] and row["active"] is None:
            line += "  (none active)"
        if row["env_override"]:
            line += f"  ({row['env']} is set in the environment and wins)"
        lines.append(line)
    lines.append("* marks the active account. Add one with "
                 "`flywheel setup --provider NAME --account LABEL`.")
    return "\n".join(lines)


def _use(provider: str, label: str) -> str:
    done = accounts.use_account(provider, label)
    if not done["changed"]:
        return f"{provider} already uses the account '{label}'"
    text = f"{provider} now uses the account '{label}'"
    return f"{text}; {done['note']}" if done["note"] else text


def _remove(provider: str, label: str) -> str:
    done = accounts.remove_account(provider, label)
    text = f"removed the account '{label}' for {provider}"
    if not done["key_found"]:
        text += " (no stored key was found for it)"
    if done["was_active"] and done["remaining"]:
        text += (f"; no account is active now, choose one with "
                 f"`flywheel auth use {provider} {done['remaining'][0]}`")
    return text


def _account_verb(verb: str, args: list) -> int:
    try:
        if verb == "list":
            print(render_list(accounts.list_accounts()))
            return 0
        if len(args) != 2:
            print(f"usage: flywheel auth {verb} PROVIDER LABEL", file=sys.stderr)
            return 2
        print(_use(*args) if verb == "use" else _remove(*args))
        return 0
    except accounts.AccountsError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def main(argv: "list[str] | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv) or (argv and argv[0] == "help"):
        print("usage: flywheel auth <command>\n" + USAGE)
        return 0
    args = [a for a in argv if not a.startswith("-")]
    if args and args[0] in _ACCOUNT_VERBS:
        return _account_verb(args[0], args[1:])
    if args and args[0] not in ("status", "login", "logout"):
        print(f"`flywheel auth {args[0]}` is not a command.\n" + USAGE, file=sys.stderr)
        return 2
    from harness.oauth_signin import cli as _signin_cli
    return _signin_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
