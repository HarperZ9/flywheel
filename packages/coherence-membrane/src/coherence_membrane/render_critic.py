"""Render-critic -- wire the vintage renderer to the grounded critic + memory.

render -> perceive -> critique(compose[novelty vs corpus, structural fitness =
OKLab-dE source-vs-output fidelity]) -> remember, as a generator yielding witnessed
step events. Composes shipped parts; retro.py untouched. Stdlib only; inert.
"""
from __future__ import annotations

from dataclasses import dataclass

from .certificate import Verdict
from .color import delta_e_ok
from .color_field import color_field_from_png, downscale_color_field
from .composition import compose
from .memory import MemoryRecord, MemoryStore
from .novelty import novelty_criterion
from .observation import Observation, Provenance, Status
from .phash import hamming, perceptual_hash
from .pngview import PngDecodeError, decode_png
from .recall import recall
from .retro import render_vintage
from .structural_fitness import structural_fitness_criterion

FIDELITY_CW = 64


def render_fidelity_deviation(form) -> float:
    """Mean OKLab dE between source and output, downscaled to a common grid.
    `form = (source_png, output_png)`. inf when nothing comparable (fail-closed)."""
    source_png, output_png = form
    src = color_field_from_png(source_png)
    out = color_field_from_png(output_png)
    cw = min(src.width, out.width, FIDELITY_CW)
    ch = max(1, round(cw * src.height / src.width))
    ch = min(ch, src.height, out.height)
    s = downscale_color_field(src, cw, ch)
    o = downscale_color_field(out, cw, ch)
    diffs = [delta_e_ok(s.lab[i], o.lab[i]) for i in range(cw * ch)
             if not s.unknown[i] and not o.unknown[i]]
    if not diffs:
        return float("inf")
    return sum(diffs) / len(diffs)


def render_signature(output_png: bytes) -> int:
    """The novelty signature of a render: 64-bit dHash of its output PNG."""
    return perceptual_hash(decode_png(output_png))


def critique_render(render_result, source_png, *, corpus, min_distance, tolerance) -> Observation:
    """Judge a render novel-vs-corpus AND structurally faithful; one witnessed Observation.
    Fail-closed: an undecodable render/source yields a reasoned UNVERIFIABLE, never raises."""
    try:
        signature = render_signature(render_result.output_png)
        deviation = render_fidelity_deviation((source_png, render_result.output_png))
    except PngDecodeError as exc:
        return Observation(
            "render-critic", render_result.output_sha256, "render critique: unverifiable",
            Status.UNVERIFIED,
            Provenance.witness_bytes(render_result.output_sha256, render_result.output_png, "low"),
            {"verdict": "unverifiable",
             "evidence": [["decode", "unverifiable", f"undecodable PNG: {exc}"]],
             "signature": None, "deviation": None,
             "palette_hex": list(render_result.palette_hex)},
        )
    nov = novelty_criterion(corpus, distance=hamming, min_distance=min_distance).judge(signature)
    fit = structural_fitness_criterion(lambda _f: deviation, tolerance=tolerance).judge(None)
    cert = compose([nov, fit], claim="render is novel AND structurally faithful")
    decided = cert.verdict in (Verdict.VERIFIED, Verdict.REFUTED)
    return Observation(
        "render-critic", render_result.output_sha256, f"render critique: {cert.verdict.value}",
        Status.PASS if decided else Status.UNVERIFIED,
        Provenance.witness_bytes(render_result.output_sha256, render_result.output_png,
                                 "high" if decided else "low"),
        {"verdict": cert.verdict.value,
         "evidence": [list(e) for e in cert.evidence],
         "signature": signature, "deviation": deviation,
         "palette_hex": list(render_result.palette_hex)},
    )


def remember_render(store: MemoryStore, render_result, observation) -> str:
    """Store a render-look as a witnessed memory; its perceptual signature joins the
    corpus *inside* the witnessed MemoryRecord (a phash: tag) -- covered by verify() and
    round-tripped by save/load. Idempotent and signature-aware: re-remembering the same
    render, or an undecodable one (no signature), is a no-op return, never a crash."""
    rid = render_result.output_sha256
    signature = observation.data.get("signature")
    if signature is None or rid in store.records:
        return rid
    record = MemoryRecord(
        id=rid, type="pref", claim=rid,
        tags=("render", f"{_PHASH_TAG}{signature}"),
    )
    store.remember(record)
    return rid


_PHASH_TAG = "phash:"


def render_corpus(store: MemoryStore) -> list[int]:
    """Perceptual signatures of all remembered renders = the novelty corpus, recalled
    from witnessed memory (no side-channel state)."""
    out: list[int] = []
    for r in recall(store, tags=("render",)):
        for t in r.record.tags:
            if t.startswith(_PHASH_TAG):
                out.append(int(t[len(_PHASH_TAG):]))
                break
    return out


@dataclass(frozen=True)
class RenderStep:
    name: str            # render | perceive | critique | remember
    observation: Observation
    payload: dict


def render_and_critique(source_png, render_params, store, *, min_distance, tolerance):
    """Generator: render -> perceive -> critique -> remember, yielding a witnessed step each.
    The same witnessed stream a test, a log, or the future Perception TV view consumes."""
    result = render_vintage(source_png, **render_params)
    yield RenderStep("render", _obs("render", result.output_sha256, result.output_png,
                                    {"params": result.params, "palette_hex": list(result.palette_hex)}),
                     {"output_png": result.output_png})

    try:
        signature = render_signature(result.output_png)
        deviation = render_fidelity_deviation((source_png, result.output_png))
        perceive_data = {"signature": signature, "deviation": deviation}
        perceive_status = Status.PASS
    except PngDecodeError as exc:
        perceive_data = {"signature": None, "deviation": None, "error": str(exc)}
        perceive_status = Status.UNVERIFIED
    yield RenderStep(
        "perceive",
        Observation("render-critic:perceive", result.output_sha256, "render-critic perceive",
                    perceive_status,
                    Provenance.witness_bytes(result.output_sha256, result.output_png,
                                             "high" if perceive_status == Status.PASS else "low"),
                    perceive_data),
        perceive_data,
    )

    obs = critique_render(result, source_png, corpus=render_corpus(store),
                          min_distance=min_distance, tolerance=tolerance)
    yield RenderStep("critique", obs, {"verdict": obs.data["verdict"], "evidence": obs.data["evidence"]})

    remember_render(store, result, obs)
    yield RenderStep("remember", obs, {"corpus_size": len(render_corpus(store))})


def _obs(stage: str, subject: str, payload: bytes, data: dict) -> Observation:
    return Observation(f"render-critic:{stage}", subject, f"render-critic {stage}", Status.PASS,
                       Provenance.witness_bytes(subject, payload, "high"), data)


def run_render_critique(source_png, render_params, store, *, min_distance, tolerance):
    """Drain the watchable stream; return (RenderResult, critique Observation)."""
    result = render_vintage(source_png, **render_params)
    obs = critique_render(result, source_png, corpus=render_corpus(store),
                          min_distance=min_distance, tolerance=tolerance)
    remember_render(store, result, obs)
    return result, obs
