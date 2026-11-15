# SPDX-License-Identifier: AGPL-3.0-only
"""Back-compat shim. The shared marker-corpus loader now lives in emet/corpus.py.
Re-exported here so `import corpus` (and importlib.reload on it) keeps working;
corpus_path() reads EMET_CORPUS at call time, so behaviour is unchanged."""
from emet.corpus import *  # noqa: F401,F403
from emet.corpus import (  # noqa: F401  (explicit re-export for importlib.reload consumers)
    CorpusError, corpus_path, load, scan, count, matches_at, REPL, DEFAULT_NAME,
)
