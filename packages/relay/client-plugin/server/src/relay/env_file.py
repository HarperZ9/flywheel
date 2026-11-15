"""env_file.py -- where the remote server's settings file lives.

Kept apart from remote_state so the stdio server can keep its file tools away
from that file without loading the remote surface's settings reader.
"""
from __future__ import annotations

import os
from typing import Mapping

DEFAULT_ENV_FILE = ".env"


def env_file_path(env: Mapping[str, str] | None = None) -> str:
    """The file the remote entrypoint would read, RELAY_ENV_FILE or ``.env``."""
    env = os.environ if env is None else env
    return env.get("RELAY_ENV_FILE") or DEFAULT_ENV_FILE
