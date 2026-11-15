#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""articulate.process_commit -- salted commitments to draft text.

A draft, note or source entry stores sha256(salt || text) with a fresh random
32-byte salt, never a plain hash. With a plain hash, anyone holding a candidate
text could test it against a draft the writer chose to keep back. The salts stay
in a local file, keyed by commitment, that no default export includes; revealing
draft N releases its text and salt together, and a reader checks the pair
against the logged commitment. Keying by commitment keeps salts apart when a
continued log starts its sequence numbers again at 1.

Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets


def new_salt() -> str:
    return secrets.token_bytes(32).hex()


def commit(salt_hex: str, text: str) -> str:
    return "sha256:" + hashlib.sha256(bytes.fromhex(salt_hex) + text.encode("utf-8")).hexdigest()


def opens(commitment: str, salt_hex: str, text: str) -> bool:
    try:
        return commit(salt_hex, text) == commitment
    except ValueError:
        return False


def load_salts(path):
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_salt(path, commitment, salt_hex, text, kind="draft"):
    """Keep the salt, and a private plain hash used only to skip an unchanged
    draft. Only a reveal the writer asks for exports a salt, one per draft."""
    salts = load_salts(path)
    salts[commitment] = {"salt": salt_hex, "kind": kind,
                       "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(salts, fh, indent=1, sort_keys=True)
