"""workstream_readback.py -- does the formal statement say what the source says.

Everything else in this layer checks that a proof holds. Nothing in it checks
that the theorem is the one the paper stated, and that gap is where a verified
stack of thirty thousand lemmas quietly stops meaning anything. The audit surface
bounds who has to read what. This kind is the reading itself.

The method is read-back. A renderer is handed the formal statement WITHOUT its
source and asked to say in ordinary words what it asserts. A person then compares
that rendering against the source the statement was formalized from. Withholding
the source is the whole design: a renderer that has read the source will produce
the source's own words whether or not the formalization captured them, and the
comparison would be a mirror.

Two rules keep this from becoming a machine that grades itself.

NOTHING SETTLES ON A RENDERER'S SAY-SO. A rendering on its own is UNDECIDED. Only
a person's recorded confirmation passes, so a model never certifies its own
reading, and the default path runs no model at all: it hashes what is recorded
and compares. Model agreement is not independent ground truth, and the accept
path stays deterministic and offline for exactly that reason.

DRIFT IS NEVER A REFUTATION. A confirmation pins the formal statement, the
source, and the rendering together. Change any of the three and the pin expires
and the obligation is UNDECIDED again. It is not FAIL: nobody said the statement
was wrong, they said it has not been read in its current form. Since UNDECIDED
does not satisfy a parent, an unread read-back blocks the stack above it, which
is the property worth having.

The rendering lives in the declaration beside the obligation rather than inside
the statement, because the statement is folded into the workstream identity. A
re-render would otherwise move the identity of every obligation above it, and an
identity that moves whenever a model is asked the same question twice is not an
identity.

    {"id": "faithful", "check": "readback", "environment": "readback/v1",
     "statement": "{\\"formal\\": \\"...\\", \\"source\\": \\"...\\"}",
     "readback": {"rendering": "...", "confirmed": "<64-character pin>"}}
"""
from __future__ import annotations

from harness.evidence_json import canonical_sha256, strict_load_json
from harness.workstream import Obligation, WorkstreamError

READBACK_SCHEMA = "flywheel.workstream.readback/v1"

_MAX_DOCUMENT = 32_000_000
_MAX_STATEMENT = 20_000
_MAX_RENDERING = 20_000


def readback_pin(formal: str, source: str, rendering: str) -> str:
    """What a person's confirmation pins: all three texts, together.

    Pinning the rendering as well as the statement is what makes a re-render
    expire the reading. A confirmation is a claim about one comparison, and a
    different rendering is a different comparison.
    """
    return canonical_sha256({
        "formal": formal,
        "source": source,
        "rendering": rendering,
    })


def readback_parts(obligation: Obligation) -> tuple[str, str]:
    """The formal statement and the source it was formalized from."""
    body = strict_load_json(obligation.statement, max_bytes=_MAX_STATEMENT)
    formal = body.get("formal")
    source = body.get("source")
    if not isinstance(formal, str) or not formal.strip():
        raise ValueError("formal must be the exact statement that was formalized")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be the informal text it came from")
    return formal, source


def recorded_readbacks(document: str) -> dict[str, dict]:
    """Renderings and confirmations carried inside a declaration.

    Read here rather than in load_workstream for the same reason readings are:
    a rendering is a record about a workstream, not part of one, and a
    declaration that carries none is a complete declaration.
    """
    body = strict_load_json(document, max_bytes=_MAX_DOCUMENT)
    listed = body.get("obligations")
    if not isinstance(listed, list):
        raise WorkstreamError("a declaration carries a goal string and an obligations list")
    found: dict[str, dict] = {}
    for entry in listed:
        if not isinstance(entry, dict):
            raise WorkstreamError("every obligation is an object")
        carried = entry.get("readback")
        if carried is None:
            continue
        found[entry.get("id", "")] = _one_readback(carried)
    return found


def _one_readback(carried: object) -> dict:
    """Insist on the shape of a recorded read-back before anything reads it."""
    if not isinstance(carried, dict):
        raise WorkstreamError("readback is an object with a rendering and a confirmation")
    rendering = carried.get("rendering")
    if not isinstance(rendering, str) or not rendering.strip():
        raise WorkstreamError("readback.rendering is what the renderer said the statement means")
    if len(rendering) > _MAX_RENDERING:
        raise WorkstreamError(f"readback.rendering is under {_MAX_RENDERING} characters")
    confirmed = carried.get("confirmed")
    if confirmed is not None and (not isinstance(confirmed, str) or len(confirmed) != 64):
        raise WorkstreamError("readback.confirmed is the 64-character pin that was read")
    return {"rendering": rendering, "confirmed": confirmed}


def _render_now(formal: str, renderer) -> tuple[str, str]:
    """Ask a renderer for a fresh rendering. Never a verdict, only a rendering."""
    try:
        said = renderer(formal)
    except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
        return "UNVERIFIABLE", f"the renderer raised {type(exc).__name__}: {exc}"
    if not isinstance(said, str) or not said.strip():
        return "UNVERIFIABLE", "the renderer returned nothing to compare"
    return "UNDECIDED", (f"rendered, and nobody has compared it yet: {said[:400]}")


def readback_checker(readbacks: dict[str, dict] | None = None, renderer=None):
    """A checker over recorded read-backs, and optionally a renderer to make one.

    The renderer is handed the formal statement alone. It is never handed the
    source, and it never decides anything: its output is a rendering for a person
    to compare, and the obligation stays undecided until a person records that
    they compared it.
    """
    recorded = dict(readbacks or {})

    def check(obligation: Obligation) -> tuple[str, str]:
        try:
            formal, source = readback_parts(obligation)
        except (TypeError, ValueError) as exc:
            return "FAIL", f"the statement is not a readable read-back claim: {exc}"
        carried = recorded.get(obligation.obligation_id)
        if carried is None:
            if renderer is None:
                return "UNVERIFIABLE", ("no rendering is recorded and no renderer is "
                                        "wired, so nothing here reads this statement")
            return _render_now(formal, renderer)
        pin = readback_pin(formal, source, carried["rendering"])
        if carried["confirmed"] is None:
            return "UNDECIDED", f"rendered, awaiting a person's comparison; pin {pin}"
        if carried["confirmed"] != pin:
            # Drift, not a refutation. Something in the three texts moved after
            # the reading, and nobody has said the statement is wrong.
            return "UNDECIDED", ("the confirmation was recorded against different text, "
                                 f"so it is not carried forward; pin {pin}")
        return "PASS", f"a person compared the rendering against the source; pin {pin[:16]}"

    return check
