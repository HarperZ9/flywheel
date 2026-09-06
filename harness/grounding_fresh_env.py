"""grounding_fresh_env.py: re-run an ancestor from its receipt and nothing else.

Split out of grounding.py, which had grown past the 300-line limit while this
fallback and the resolution walk sat in one file. The seam is the one the tests
already drew: `tests/test_grounding_fresh_env.py` covers what is here and
`tests/test_citation_pin.py` covers what stayed.

The behaviour is unchanged by the move. grounding.py re-exports these names, so
`from harness.grounding import _rewitness_in_fresh_env` still resolves.
"""
from __future__ import annotations

import tempfile

from .envelope import ProofEnvelope
from .oracle_inputs import restore as restore_inputs, safe_relative as _safe_relative
from .transitive_witness import MATCH, UNVERIFIABLE
from .witness import witness_envelope

_NO_ENV = ("no oracle environment supplied for re-run — "
           "fail closed, not re-run in a wrong workdir")


def _rewitness_in_fresh_env(env: ProofEnvelope) -> tuple[str, str]:
    """Re-run an ancestor in an empty directory built from its receipt alone.

    Only reproduction is believed. See the asymmetry in grounding.py's module
    docstring: MATCH is evidence the environment sufficed, a mismatch is not
    evidence of drift, so a mismatch degrades to UNVERIFIABLE and keeps its
    reason.

    Strength depends on the oracle. For `pytest` the canonical hash folds every
    test id and outcome from the run, so reproducing it in a bare directory is
    a strong statement. For an oracle whose canonical form is empty the hash
    covers the return code only, and a fresh-environment MATCH there is worth
    no more than "it exited the same way".
    """
    rel = _safe_relative(env.candidate_path)
    if rel is None:
        return UNVERIFIABLE, (_NO_ENV + "; the envelope records no usable "
                              "candidate path to rebuild one from")
    offered = len(env.oracle_inputs or {})
    with tempfile.TemporaryDirectory(prefix="fw-grounding-") as td:
        written = restore_inputs(env.oracle_inputs, td)
        v = witness_envelope(env, workdir=td, candidate_path=rel)
    if v.verdict == MATCH:
        return MATCH, ("no workdir supplied; reproduced the canonical hash in a "
                       "fresh environment built from the envelope alone")
    return UNVERIFIABLE, (
        f"{_NO_ENV}; a fresh-environment re-run did not reproduce ({v.reason}), "
        "which does not separate drift from a missing fixture"
        + _shortfall(env, offered, written))


def _shortfall(env: ProofEnvelope, offered: int, written: int) -> str:
    """Name the fixtures that never reached the fresh directory, if any.

    A mismatch reads as tampering, and sometimes the environment was simply
    incomplete for a reason recorded on our own side. Both causes are stated
    where the verdict is, since neither is recoverable from the hash.
    """
    notes = []
    if env.withheld_inputs:
        notes.append("%d fixture(s) were withheld at seal time as "
                     "credential-bearing" % len(env.withheld_inputs))
    if written < offered:
        notes.append("this end refused %d of %d carried fixtures"
                     % (offered - written, offered))
    return ("; " + "; ".join(notes)) if notes else ""
