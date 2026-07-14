"""credo.py -- the belief, held steady across every surface, retrievable.

The project-docs of a tool family drift apart unless the belief itself is an
artifact: one canonical text, content-addressed, served by the gateway and
echoed in every README. This is that artifact. Change it here and the hash
moves everywhere it is checked.
"""
from __future__ import annotations

import hashlib

CREDO = """\
Flywheel and its tool family hold one belief steady across every surface:

1. Knowledge is an open surface for anyone who can attain the means;
   we build to lower the means.
2. The work speaks for itself: an external check decides acceptance;
   never reputation, never the model.
3. Every result carries a receipt a stranger can re-run.
4. No claim without its interval; the honest null is a first-class result.
5. Ownership is earned by comprehension: you own what you can review,
   explain, and defend.
6. Learning is woven into the work: every flagged gap is a lesson about
   your own system.
7. The badge and the contribution were bundled; we rebundle them around
   the work, not the worker.

Growth, learning, knowledge, application, ownership: in that order,
for everyone.
"""


def credo_doc() -> dict:
    return {
        "schema": "flywheel.credo/v1",
        "credo": CREDO,
        "sha256": hashlib.sha256(CREDO.encode("utf-8")).hexdigest(),
        "beliefs": 7,
    }
