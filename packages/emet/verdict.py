# SPDX-License-Identifier: AGPL-3.0-only
"""Back-compat shim. The closed verdict lattice now lives in emet/verdict.py.
Re-exported here so `import verdict` keeps working for out-of-package consumers."""
from emet.verdict import *  # noqa: F401,F403
from emet.verdict import (  # noqa: F401
    governed, VerdictError, LATTICE, COHERENCE, CORROBORATE, AUDIT,
    MONITOR_FILE, MONITOR_BASELINE, PERCEPTION, REVERT, RECEIPT, FORBIDDEN,
)
