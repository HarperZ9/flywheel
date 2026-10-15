"""setup_cli.py -- `flywheel setup`: connect a model in one step.

  flywheel setup                       what is connected, and what you can connect
  flywheel setup --provider anthropic  store that provider's API key

The key is read without echo and stored in the OS credential store (Windows
Credential Manager), where every Flywheel backend already looks after the
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

PROVIDERS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
             "gemini": "GEMINI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
             "openrouter": "OPENROUTER_API_KEY"}
CLIS = {"claude": "Claude Code (uses your Claude subscription)",
        "codex": "Codex CLI (uses your ChatGPT sign-in)"}


def status(which=shutil.which) -> list:
    from harness.keychain import credential_source
    rows = [(name, env, credential_source(env)) for name, env in PROVIDERS.items()]
    out = [f"  {name:<11} {env:<20} {source}" for name, env, source in rows]
    out += [f"  {cli:<11} {'on PATH' if which(cli) else 'not found':<20} {desc}"
            for cli, desc in CLIS.items()]
    return out


def store(provider: str, read_secret=getpass.getpass) -> "tuple[bool, str]":
    from harness import keychain
    env = PROVIDERS[provider]
    if not keychain.keychain_available():
        return False, (f"this system has no credential store Flywheel can use; set {env} "
                       f"in your shell profile instead (export {env}=...)")
    secret = read_secret(f"{env} (input hidden): ").strip()
    if not secret:
        return False, "no key entered; nothing was stored"
    result = keychain.keychain_set(env, secret)
    if isinstance(result, dict) and result.get("error"):
        return False, f"could not store the key: {result['error'].get('message', 'error')}"
    return True, f"stored {env} in the OS credential store; `flywheel code` will use it"


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel setup", description=__doc__.splitlines()[0])
    ap.add_argument("--provider", choices=sorted(PROVIDERS),
                    help="store this provider's API key")
    args = ap.parse_args(argv)
    if args.provider:
        ok, message = store(args.provider)
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    print("Models Flywheel can use:")
    print("\n".join(status()))
    print("Connect one with `flywheel setup --provider anthropic` (or openai, gemini, "
          "deepseek, openrouter), sign in to the claude or codex CLI, or start a local "
          "server such as ollama.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
