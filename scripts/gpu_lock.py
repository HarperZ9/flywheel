"""gpu_lock.py -- a directory lock for one shared GPU, with an owner check on release.

Acquire creates the lock directory atomically (mkdir fails if it exists) and
writes an OWNER file naming the process, the purpose and a random token. Release
removes the lock only when OWNER still carries the caller's token, so one job can
never free a lock another job holds.

    python scripts/gpu_lock.py acquire DIR --purpose "..."   # prints the token
    python scripts/gpu_lock.py release DIR --token TOKEN
    python scripts/gpu_lock.py show DIR
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path


class LockError(RuntimeError):
    """The lock is held by someone else, or OWNER does not name the caller."""


def owner(lock_dir) -> dict | None:
    try:
        return json.loads((Path(lock_dir) / "OWNER").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def acquire(lock_dir, purpose: str, session: str = "") -> str:
    """Create the lock or raise LockError naming the holder. Returns the token."""
    lock = Path(lock_dir)
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise LockError(f"held: {owner(lock)}") from exc
    token = secrets.token_hex(16)
    record = {"pid": os.getpid(), "purpose": purpose, "session": session, "token": token,
              "since": datetime.now(timezone.utc).isoformat()}
    (lock / "OWNER").write_text(json.dumps(record), encoding="utf-8")
    return token


def release(lock_dir, token: str) -> None:
    """Remove the lock if OWNER carries `token`; otherwise raise and leave it."""
    lock = Path(lock_dir)
    rec = owner(lock)
    if rec is None or rec.get("token") != token:
        raise LockError(f"not the owner; OWNER is {rec}")
    (lock / "OWNER").unlink()
    lock.rmdir()


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("acquire", "release", "show"))
    p.add_argument("lock_dir")
    p.add_argument("--purpose", default="")
    p.add_argument("--token", default="")
    a = p.parse_args(argv)
    try:
        if a.action == "acquire":
            print(acquire(a.lock_dir, a.purpose))
        elif a.action == "release":
            release(a.lock_dir, a.token)
            print("released")
        else:
            print(json.dumps(owner(a.lock_dir)))
    except LockError as exc:
        print(f"gpu_lock: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
