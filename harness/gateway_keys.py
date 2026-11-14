"""gateway_keys.py -- virtual keys for the gateway's model interfaces.

A virtual key is a local credential the owner hands to one tool or one
teammate. It opens /v1/messages, /v1/messages/count_tokens and /v1/responses
and no other gateway route. Each key has a name, optional limits and an
optional model allow-list, and the gateway keeps running totals for it.

Two places hold a key's state:

  the credential store   the raw key, under `flywheel/FLYWHEEL_GATEWAY_KEY@<name>`
                         (harness.keychain). Nothing else holds it.
  FLYWHEEL_HOME/gateway-keys.json
                         facts that are not secret: the name, a fingerprint
                         (the first 16 hex characters of the key's SHA-256),
                         limits, prices, the allow-list, the created time, the
                         revoked flag and the running totals.

The credential store is the authority. `authenticate` finds a candidate row by
fingerprint and then compares the offered key with the stored one, so a process
that can write the index and nothing else cannot mint a working key. Revoking
deletes the stored key as well as setting the flag.

Totals. `tokens` is every token the provider counted for the key's calls, each
counted once: uncached input, cache read, cache write and output. Spend is
(uncached input + cache read + cache write) at the key's input price plus
output at its output price, both in USD per million tokens. No price table
ships; a spend limit needs both prices. A call whose provider sent no counts
is charged the whitespace word estimate (token_usage.estimate) and counted in
`estimated_calls` and `estimated_tokens`.

A key never appears in the index, in a row this module returns, in an error
text or in a log record. `create` returns it once.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from decimal import Decimal
from hmac import compare_digest
from pathlib import Path

PREFIX = "fwk_"
SLOT = "FLYWHEEL_GATEWAY_KEY"
INDEX = "gateway-keys.json"
COUNTS = ("input", "output", "cache_read", "cache_write")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}\Z")
_ZERO = {"calls": 0, "tokens": 0, "input_tokens": 0, "output_tokens": 0,
         "cache_read_tokens": 0, "cache_write_tokens": 0,
         "estimated_calls": 0, "estimated_tokens": 0}
_THREADS = threading.Lock()             # one reader or writer of the index per process
_LOG = logging.getLogger(__name__)
WARM = os.name == "nt"                  # open the index after a debit; see Keys._warm


class KeysError(Exception):
    """A key request that cannot be carried out. The text is safe to print."""


def fingerprint(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def spend(row: dict) -> "float | None":
    """USD spent so far at the key's prices, or None when it has no prices."""
    if row.get("price_in") is None or row.get("price_out") is None:
        return None
    totals = row["totals"]
    inp = totals["input_tokens"] + totals["cache_read_tokens"] + totals["cache_write_tokens"]
    usd = (inp * Decimal(str(row["price_in"]))
           + totals["output_tokens"] * Decimal(str(row["price_out"]))) / 1_000_000
    return float(round(usd, 8))


def over(row: dict) -> "tuple | None":
    """(reason, sentence) when the totals are at or over a limit, else None."""
    used, limit = row["totals"]["tokens"], row.get("token_limit")
    if limit is not None and used >= limit:
        return "token_limit", f"its token limit ({used} of {limit} tokens used)"
    spent, limit = spend(row), row.get("spend_limit")
    if limit is not None and spent is not None and spent >= limit:
        return "spend_limit", f"its spend limit (${spent:.6f} of ${limit:.6f} spent)"
    return None


def _store():
    from .accounts import KeychainStore
    return KeychainStore()


def _amount(value, what: str, whole: bool = False):
    if value is None:
        return None
    bad = isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
    if bad or value != value or value == float("inf") or (whole and int(value) != value):
        raise KeysError(f"{what} must be a {'whole ' if whole else ''}number, zero or more")
    return int(value) if whole else float(value)


class Keys:
    """The keys of one Flywheel home. `store` has available/get/set/delete."""

    def __init__(self, home, store=None, clock=time.time):
        self.path, self.store, self.clock = Path(home) / INDEX, store or _store(), clock

    @contextmanager
    def _held(self):
        """One writer at a time: across threads, and across processes by a lock file."""
        from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
        with _THREADS:
            try:
                with ExclusiveJourneyLock.acquire(self.path.with_name(INDEX + ".lock"), 5.0):
                    yield
            except JourneyLockBusy as exc:
                raise KeysError("the gateway key list is locked by another process") from exc

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise KeysError(f"cannot read the gateway key list ({type(exc).__name__}); "
                            f"fix or remove {INDEX} in the Flywheel home") from exc
        rows = data.get("keys") if isinstance(data, dict) else None
        return {name: row for name, row in (rows if isinstance(rows, dict) else {}).items()
                if _NAME.match(str(name)) and _well_formed(row)}

    def _write(self, rows: dict) -> None:
        tmp = self.path.with_name(INDEX + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps({"version": 1, "keys": rows}, indent=2, sort_keys=True),
                           encoding="utf-8")
            for attempt in range(5):        # a reader in another process holds it open
                try:
                    return os.replace(tmp, self.path)
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.01)
        except OSError as exc:
            raise KeysError(f"cannot write the gateway key list ({type(exc).__name__})") from exc

    def rows(self) -> dict:
        with _THREADS:
            return self._read()

    def row(self, name: str) -> dict:
        found = self.rows().get(name)
        if found is None:
            raise KeysError(f"no gateway key named '{name}'")
        return found

    def create(self, name: str, *, token_limit=None, spend_limit=None, price_in=None,
               price_out=None, models=()) -> tuple:
        """Mint a key. Returns (raw key, row); the raw key is not kept anywhere else."""
        if not isinstance(name, str) or not _NAME.match(name):
            raise KeysError("a key name is 1 to 32 characters: letters, digits, dot, dash "
                            "or underscore, starting with a letter or digit")
        row = {"token_limit": _amount(token_limit, "--token-limit", whole=True),
               "spend_limit": _amount(spend_limit, "--spend-limit"),
               "price_in": _amount(price_in, "--price-in"),
               "price_out": _amount(price_out, "--price-out"),
               "models": sorted({str(m).strip() for m in models if str(m).strip()}),
               "created": int(self.clock()), "revoked": False, "totals": dict(_ZERO)}
        if (row["price_in"] is None) != (row["price_out"] is None):
            raise KeysError("give both --price-in and --price-out, or neither")
        if row["spend_limit"] is not None and row["price_in"] is None:
            raise KeysError("a spend limit needs --price-in and --price-out (USD per million "
                            "tokens); no price table ships with Flywheel")
        if not self.store.available():
            from . import keychain
            raise KeysError("no system credential store can hold the key: "
                            f"{keychain.keychain_refusal() or 'none was found'}")
        with self._held():
            rows = self._read()
            if name in rows:
                raise KeysError(f"a gateway key named '{name}' already exists; revoke it or "
                                "choose another name")
            raw = PREFIX + secrets.token_urlsafe(32)
            row["fingerprint"] = fingerprint(raw)
            from .accounts import error_text
            problem = error_text(self.store.set(f"{SLOT}@{name}", raw))
            if problem:
                raise KeysError(f"the credential store refused the key: {problem}")
            rows[name] = row
            self._write(rows)
        return raw, row

    def revoke(self, name: str) -> dict:
        """Set the revoked flag and delete the stored key. The totals are kept."""
        with self._held():
            rows = self._read()
            if name not in rows:
                raise KeysError(f"no gateway key named '{name}'")
            rows[name]["revoked"] = True
            self._write(rows)
            self.store.delete(f"{SLOT}@{name}")
        return rows[name]

    def reset(self, name: str) -> dict:
        """Zero the running totals of a key."""
        with self._held():
            rows = self._read()
            if name not in rows:
                raise KeysError(f"no gateway key named '{name}'")
            rows[name]["totals"] = dict(_ZERO)
            self._write(rows)
        return rows[name]

    def authenticate(self, offered) -> "tuple | None":
        """(name, row) for a key the credential store holds, else None."""
        if not isinstance(offered, str) or not offered.startswith(PREFIX) or len(offered) > 200:
            return None
        mark = fingerprint(offered)
        for name, row in self.rows().items():
            if row["fingerprint"] != mark:
                continue
            stored = self.store.get(f"{SLOT}@{name}")
            if stored and compare_digest(stored.encode("utf-8"), offered.encode("utf-8")):
                return name, row
        return None

    def debit(self, name: str, counts: dict, estimated: bool = False) -> dict:
        """Add one call's counts to a key's totals; returns the row after it."""
        with self._held():
            rows = self._read()
            row = rows.get(name)
            if row is None:
                raise KeysError(f"no gateway key named '{name}'")
            totals, spent = row["totals"], 0
            for key in COUNTS:
                amount = counts.get(key) or 0
                totals[f"{key}_tokens"] += amount
                spent += amount
            totals["calls"] += 1
            totals["tokens"] += spent
            if estimated:
                totals["estimated_calls"] += 1
                totals["estimated_tokens"] += spent
            self._write(rows)
        if WARM:
            threading.Thread(target=self._warm, daemon=True).start()
        return row

    def _warm(self) -> None:
        """Open the index once, on a thread of its own, after a debit changed it.

        On Windows with real-time file scanning the first open of a file with
        new contents waits for the scan (6 ms measured, docs/BENCHMARKS.md).
        Paying that here keeps it out of the next call's key check. The bytes
        are thrown away: every check and every debit still reads the file."""
        try:
            with _THREADS:
                self.path.read_bytes()
        except OSError as exc:
            _LOG.debug("gateway key list not opened after a debit (%s)", type(exc).__name__)


def _well_formed(row) -> bool:
    totals = row.get("totals") if isinstance(row, dict) else None
    return (isinstance(totals, dict) and isinstance(row.get("fingerprint"), str)
            and all(type(totals.get(key)) is int for key in _ZERO)
            and isinstance(row.get("models"), list))


def view(name: str, row: dict) -> dict:
    """A row as the CLI shows it: the stored facts plus spend and what is left."""
    spent, left = spend(row), {}
    if row.get("token_limit") is not None:
        left["tokens"] = max(0, row["token_limit"] - row["totals"]["tokens"])
    if row.get("spend_limit") is not None and spent is not None:
        left["spend_usd"] = max(0.0, round(row["spend_limit"] - spent, 8))
    return {"name": name, **row, "spend_usd": spent, "remaining": left}
