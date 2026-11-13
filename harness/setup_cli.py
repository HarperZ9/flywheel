"""setup_cli.py -- `flywheel setup`: connect a model in one step.

  flywheel setup                       what is connected, and what you can connect
  flywheel setup --provider anthropic  store that provider's API key
  flywheel setup --provider openai --account work
                                       store a second key under a label; switch
                                       with `flywheel auth use openai work`

The key is read without echo, tested with one models-list request to the
provider (no completion; skip the test with --no-check), and stored in the OS
credential store, where every Flywheel backend already looks after the
environment. Flywheel never writes a provider key to a plain file: on a system
without a supported credential store, setup prints the environment variable to
set instead. A stored key is never printed again; `flywheel doctor` reports it
by name only.
"""
from __future__ import annotations

import argparse
import getpass
import shutil
import sys

from harness.accounts import DEFAULT, PROVIDERS, AccountsError

CLIS = {"claude": "Claude Code (uses your Claude subscription)",
        "codex": "Codex CLI (uses your ChatGPT sign-in)"}


def status(which=shutil.which) -> list:
    from harness.keychain import credential_source
    rows = [(name, env, credential_source(env)) for name, env in PROVIDERS.items()]
    out = [f"  {name:<11} {env:<20} {source}" for name, env, source in rows]
    out += [f"  {cli:<11} {'on PATH' if which(cli) else 'not found':<20} {desc}"
            for cli, desc in CLIS.items()]
    return out


def store(provider: str, read_secret=None, account: str = DEFAULT,
          store_backend=None, index=None, check=None) -> "tuple[bool, str]":
    """Read a key and store it. `check` is a callable (provider, key) ->
    (True | False | None, line); with one, the key is stored only on True."""
    from harness import accounts, keychain
    env = PROVIDERS[provider]
    if accounts.label_error(account):
        return False, accounts.label_error(account)
    if not keychain.keychain_available():
        return False, (f"this system has no credential store Flywheel can use; set {env} "
                       f"in your shell profile instead (export {env}=...)")
    secret = (read_secret or getpass.getpass)(f"{env} (input hidden): ").strip()
    if not secret:
        return False, "no key entered; nothing was stored"
    tested = ""
    if check is not None:
        works, line = check(provider, secret)
        if works is not True:
            return False, (f"{line}\nNothing was stored. To store a key without "
                           f"testing it, add --no-check.")
        tested = line + "\n"
    try:
        done = accounts.add_account(provider, account, secret,
                                    store=store_backend, path=index)
    except AccountsError as exc:
        return False, str(exc)
    if done["active"]:
        return True, (f"{tested}stored {env} in the OS credential store as the account "
                      f"'{account}'; `flywheel code` will use it")
    return True, (f"{tested}stored the account '{account}' for {provider}; another account is "
                  f"active, switch with `flywheel auth use {provider} {account}`")


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel setup", description=__doc__.splitlines()[0])
    ap.add_argument("--provider", choices=sorted(PROVIDERS),
                    help="store this provider's API key")
    ap.add_argument("--account", default=DEFAULT, metavar="LABEL",
                    help="name for this key, so a provider can hold more than one "
                         "(default: default)")
    ap.add_argument("--no-check", action="store_true",
                    help="store the key without asking the provider whether it works")
    args = ap.parse_args(argv)
    if args.provider:
        from harness import key_check
        ok, message = store(args.provider, account=args.account,
                            check=None if args.no_check else key_check.check_key)
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    print("Models Flywheel can use:")
    print("\n".join(status()))
    print("Connect one with `flywheel setup --provider anthropic` (or openai, gemini, "
          "deepseek, openrouter), sign in to the claude or codex CLI, or start a local "
          "server such as ollama. `flywheel auth list` shows the stored accounts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
