"""client.py -- the agent-side caller. It holds no key and can only ask.

Configured by two environment variables, read when a record store opens:

  * ``FLYWHEEL_SIGNER``: the signer's address (a Unix socket path, or a
    ``\\\\.\\pipe\\...`` name on Windows). Unset means no signer: records are
    sealed but unsigned, as before, and the verifier reports them UNANCHORED.
  * ``FLYWHEEL_SIGNER_PUBKEY``: the signer's public key, hex. When set, every
    attestation is checked against it before the record is written, so a
    process squatting on the signer's address cannot get a record accepted.

A configured signer that cannot be reached, or that refuses, raises
SignerUnavailable. The record store turns that into RecordWriteError, and the
hook fails closed: the call does not run.
"""
from __future__ import annotations

import os

from . import statement
from .server import transport

ENV_ADDRESS = "FLYWHEEL_SIGNER"
ENV_PUBKEY = "FLYWHEEL_SIGNER_PUBKEY"


class SignerUnavailable(RuntimeError):
    """The configured signer could not attest a record."""


class SignerClient:
    def __init__(self, address: str, pinned_public_hex: str = "", timeout: float = 5.0):
        self.address = address
        self.pinned = bytes.fromhex(pinned_public_hex) if pinned_public_hex else None
        self.timeout = timeout

    def _call(self, request: dict) -> dict:
        try:
            reply = transport().call(self.address, request, self.timeout)
        except OSError as exc:
            raise SignerUnavailable(f"signer unreachable at {self.address}: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 -- any wire failure means no signature
            raise SignerUnavailable(f"signer reply unreadable: {exc}") from exc
        if not reply.get("ok"):
            raise SignerUnavailable(
                f"signer refused: {reply.get('error')}: {reply.get('detail', '')}")
        return reply

    def _checked(self, signed: dict, schema: str) -> dict:
        if self.pinned is None:
            return signed
        ok, why = statement.check(signed, self.pinned, schema)
        if not ok:
            raise SignerUnavailable(f"signature fails the pinned key: {why}")
        return signed

    def hello(self) -> dict:
        return self._call({"op": "hello"})

    def sign_record(self, store: str, seq: int, prev: str, seal: str) -> dict:
        reply = self._call({"op": "sign_record", "store": store, "seq": seq,
                            "prev": prev, "seal": seal})
        return self._checked(reply["attestation"], statement.ATTESTATION_SCHEMA)

    def check_policy(self, tool: str, args: dict, path_id: str = "E1") -> dict:
        from .policy import POLICY_SCHEMA
        reply = self._call({"op": "check_policy", "tool": tool, "args": args,
                            "path_id": path_id})
        return self._checked(reply["policy"], POLICY_SCHEMA)

    def head(self, store: str) -> dict:
        reply = self._call({"op": "head", "store": store})
        return self._checked(reply["head"], statement.HEAD_SCHEMA)


def client_from_env(environ=None) -> SignerClient | None:
    env = os.environ if environ is None else environ
    address = env.get(ENV_ADDRESS, "").strip()
    if not address:
        return None
    return SignerClient(address, env.get(ENV_PUBKEY, "").strip())
