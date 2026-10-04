"""lean_binding_judge.py -- the step order and the receipt of a bound check.

harness/lean_binding.py prepares the steps (live processes or an injected
runner); this module runs them in order and writes the one receipt shape
every exit returns. Each step runs only when the one before it passed, and
the compiled module's hash is rechecked after every step that follows the
compile, so all of them judge the same artifact.

`kernels_agreeing` counts the independent kernels that accepted the pinned
theorem in that artifact: Lean's (the compile and the leanchecker replay)
and nanoda (harness/lean_external_kernel.py). `passed` is True only at 2.
"""
from __future__ import annotations

import hashlib

from .lean_binding import (AXIOMS_SOURCE, KERNEL, R_BIND, R_CHALLENGE,
                           R_EXT_ERROR, R_EXT_MISSING, R_HASH, R_SANDBOX,
                           R_SHADOW, R_UNSUPPORTED, SCHEMA, SPEC_FIDELITY,
                           _bind_doc, challenge_sha256, challenge_source)

NOTE = ("the candidate compiled once; the pinned theorem was matched to the "
        "challenge's elaborated statement and every definition it uses; its "
        "axioms were walked from the compiled module and audited against the "
        "classical trio; leanchecker replayed the same module; nanoda, a "
        "second kernel, checked a lean4export export of that module. Re-run "
        "under the named toolchain and the pinned external tools to "
        "re-derive")
_CHANGED = ("the compiled module changed between checks, so the steps did not "
            "judge one artifact; fail closed")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def receipt(sha: str, passed, toolchain: str, output: str, ch: dict, *,
            bind: "dict | None" = None, level: str = "none", replay=None,
            reason: str = "", artifact: str = "", external=None,
            agreeing: int = 0, sandbox=None) -> dict:
    """The receipt of a bound check, at every exit."""
    from .lean_external_kernel import not_run
    from .lean_oracle import _ALLOWED_AXIOMS
    from .lean_replay import LADDER
    bind = bind or {}
    canonical = bind.get("statement_canonical", "") or ""
    axioms = list(bind.get("axioms", []) or [])
    name = ch.get("theorem", "")
    doc = {
        "schema": SCHEMA, "passed": passed, "code_sha256": sha,
        "toolchain": toolchain, "kernel_output": (output or "").strip()[:2000],
        "note": NOTE, "validation_level": level,
        "validation_ladder": list(LADDER), "leanchecker": replay,
        "statement_binding": "pinned" if ch else "unpinned",
        "challenge": {"theorem": name,
                      "challenge_sha256": challenge_sha256(ch) if ch else "",
                      "statement_canonical": canonical},
        "statement_sha256": _sha(canonical),
        "binding": {"status": bind.get("status", "not-run"),
                    "refusals": list(bind.get("refusals", []) or [])},
        "trusted_base": {
            "lean_version": bind.get("lean_version", ""),
            "lean_githash": bind.get("lean_githash", ""),
            "toolchain": toolchain, "kernel": KERNEL,
            "axioms_used": axioms,
            "axioms_allowed": sorted(_ALLOWED_AXIOMS),
            "axioms_source": AXIOMS_SOURCE},
        "spec_fidelity": dict(SPEC_FIDELITY),
        "artifact_sha256": artifact,
        "axiom_footprint": {name: axioms} if bind.get("axioms") is not None
        and name else {},
        "external_kernel": external or not_run(),
        "kernels_agreeing": agreeing,
        "sandbox": sandbox,
    }
    if reason:
        doc["unverifiable_reason"] = reason
    return doc


def _bind_step(code: str, ch: dict, steps, sha: str, toolchain: str,
               art: str) -> "tuple[dict | None, dict]":
    """Run the bind script. Returns (final receipt or None, bind doc)."""
    def stop(passed, text, **kw):
        return receipt(sha, passed, toolchain, text, ch, artifact=art,
                       level=kw.pop("level", "exit_code"), **kw)
    rc, out = steps.bind(code, ch["theorem"])
    if rc is None:
        return stop(None, out, reason=R_SHADOW), {}
    doc = _bind_doc(out)
    status = doc.get("status")
    if status == "unsupported":
        return stop(None, doc.get("detail", ""), bind=doc,
                    reason=R_UNSUPPORTED), doc
    if status == "refused" or (status == "bound" and doc.get("refusals")):
        return stop(False, "the candidate does not prove the pinned "
                    "statement: " + "; ".join(doc.get("refusals") or []),
                    bind=doc), doc
    if status != "bound" or doc.get("theorem") != ch["theorem"]:
        return stop(None, "the bind check judged nothing: "
                    + str(doc.get("detail", ""))[:600], bind=doc,
                    reason=R_BIND), doc
    pinned = ch.get("statement_sha256") or ""
    if pinned and pinned != _sha(doc.get("statement_canonical", "")):
        return stop(None, "the challenge statement elaborated to a form "
                    "whose hash differs from the one the task pinned",
                    bind=doc, reason=R_HASH), doc
    return None, doc


def judge(code: str, ch: dict, steps, sha: str, toolchain: str) -> dict:
    """Compile, bind, audit, replay, re-check with the second kernel; the
    first step that does not pass decides the receipt."""
    from .lean_oracle import _ALLOWED_AXIOMS, _uses_hole
    from .lean_replay import LADDER, R_COMPILE
    try:
        rc, out = steps.compile_candidate(code)
    except OSError as exc:
        return receipt(sha, None, toolchain, f"lean could not be started "
                       f"({exc})", ch, reason=R_COMPILE)
    box = getattr(steps, "sandbox", None)
    if rc is None:
        return receipt(sha, None, toolchain, "the candidate was not compiled: "
                       + (out or ""), ch, reason=R_SANDBOX, sandbox=box)
    if rc != 0 or _uses_hole(out):
        return receipt(sha, False, toolchain, out, ch, sandbox=box)
    art = steps.olean_sha()

    def stop(passed, text, **kw):
        kw.setdefault("artifact", art)
        return receipt(sha, passed, toolchain, text, ch, sandbox=box, **kw)
    rc, cout = steps.compile_challenge(challenge_source(ch))
    if rc != 0:
        return stop(None, "the pinned challenge did not compile, so nothing "
                    "can be bound to it: " + cout, level=LADDER[0],
                    reason=R_CHALLENGE)
    if steps.olean_sha() != art:
        return stop(False, _CHANGED)
    final, doc = _bind_step(code, ch, steps, sha, toolchain, art)
    if final is not None:
        final["sandbox"] = box
        return final
    forbidden = sorted(a for a in doc.get("axioms", [])
                       if a not in _ALLOWED_AXIOMS)
    if forbidden:
        return stop(False, "the pinned theorem depends on axioms outside the "
                    "classical trio: " + ", ".join(forbidden), bind=doc,
                    level=LADDER[0])
    return _kernels(code, ch, steps, doc, out, stop, toolchain, art)


def _kernels(code, ch, steps, doc, out, stop, toolchain, art) -> dict:
    """The leanchecker replay, then the second kernel, on one artifact."""
    from .lean_external_kernel import (ACCEPTED, REJECTED, UNAVAILABLE,
                                       external_check)
    from .lean_replay import LADDER, MODE, MODULE, VERSION_SOURCE
    rep = steps.replay(code)
    if steps.olean_sha() != art:
        return stop(False, _CHANGED, bind=doc)
    record = {"mode": MODE, "module": MODULE, "exit": rep.get("exit"),
              "version": toolchain,
              "version_source": VERSION_SOURCE}
    if rep["ok"] is None:
        return stop(None, "bound and audited, but the leanchecker replay "
                    "judged nothing: " + rep["detail"], bind=doc,
                    level=LADDER[1], replay=record,
                    reason=rep.get("reason") or R_BIND)
    if rep["ok"] is False:
        return stop(False, "bound and audited, but " + rep["detail"],
                    bind=doc, level=LADDER[1], replay=record)
    make = getattr(steps, "external_steps", None)
    ext = external_check(make(code, challenge_source(ch)) if make else None,
                         ch, doc)
    common = dict(bind=doc, level=LADDER[2], replay=record, external=ext)
    if steps.olean_sha() != art:
        return stop(False, _CHANGED, **common)
    if ext["verdict"] == ACCEPTED:
        return stop(True, out, agreeing=2, **common)
    if ext["verdict"] == REJECTED:
        return stop(False, "the Lean kernel accepted the pinned theorem and "
                    "the external kernel did not; the kernels disagree, so "
                    "fail closed: " + ext["detail"], agreeing=1, **common)
    reason = R_EXT_MISSING if ext["verdict"] == UNAVAILABLE else R_EXT_ERROR
    return stop(None, "the Lean kernel accepted the pinned theorem, but the "
                "external kernel judged nothing, and one kernel does not make "
                "a pass: " + ext["detail"], agreeing=1, reason=reason,
                **common)
