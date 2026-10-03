"""cost_floor.py -- measured time beside the fastest time the hardware allows.

A generation call does two kinds of work. Prefill multiplies every prompt token
through the weights; decode reads all the weights once per step to make one
token per sequence in the batch. Each phase can go no faster than the slower of
two limits: arithmetic at the chip's peak rate, and reading the weights at the
memory's peak bandwidth. The sum is a floor (a speed-of-light bound): no kernel
on that chip can beat it. The receipt gives measured time, the floor, and their
ratio, so time lost to software, queueing or a poor kernel is visible.

The floor ignores KV-cache reads, activations and network time, so it sits
below anything reachable; a ratio near 1 is the limit, not the goal of a
typical local server.
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA = "flywheel.cost-floor/v1"
DOES_NOT_PROVE = ("The floor is a lower bound from published peak rates. It does not show what "
                  "a real kernel can reach on this machine, and the ratio does not show where "
                  "the lost time went.")


@dataclass(frozen=True)
class Hardware:
    name: str
    mem_bandwidth_gbs: float      # GB/s (1e9 bytes per second)
    peak_tflops: float            # dense tensor rate used for the arithmetic floor
    rate_basis: str
    source: str


HARDWARE = {
    "rtx-4090": Hardware(
        name="NVIDIA GeForce RTX 4090", mem_bandwidth_gbs=1008.0, peak_tflops=330.3,
        rate_basis="dense FP16 tensor, FP16 accumulate",
        source="NVIDIA Ada GPU Architecture whitepaper v2.02, Appendix A"),
}


@dataclass(frozen=True)
class ModelProfile:
    params: int                   # parameter count
    weight_bytes: int             # bytes read per decode step (the weight file size)


def _phase_floor(flops: float, bytes_read: float, hw: Hardware) -> tuple[float, str]:
    compute = flops / (hw.peak_tflops * 1e12)
    memory = bytes_read / (hw.mem_bandwidth_gbs * 1e9)
    return (compute, "compute") if compute >= memory else (memory, "memory")


def floor_seconds(prompt_tokens: int, completion_tokens: int, model: ModelProfile,
                  hw: Hardware, batch: int = 1) -> dict:
    """Floor for one call (batch = sequences decoded together, each with these counts)."""
    if batch < 1 or prompt_tokens < 0 or completion_tokens < 0:
        raise ValueError("batch must be at least 1 and token counts non-negative")
    prefill, pre_bound = _phase_floor(2.0 * model.params * prompt_tokens * batch,
                                      model.weight_bytes, hw)
    step, dec_bound = _phase_floor(2.0 * model.params * batch, model.weight_bytes, hw)
    decode = step * completion_tokens
    return {"prefill_s": prefill, "prefill_bound": pre_bound,
            "decode_s": decode, "decode_bound": dec_bound,
            "floor_s": prefill + decode}


def receipt(measured_s: float, prompt_tokens: int, completion_tokens: int,
            model: ModelProfile, hardware: str | Hardware, batch: int = 1) -> dict:
    """One cost receipt: measured time against the hardware floor."""
    hw = HARDWARE[hardware] if isinstance(hardware, str) else hardware
    f = floor_seconds(prompt_tokens, completion_tokens, model, hw, batch)
    ratio = measured_s / f["floor_s"] if f["floor_s"] > 0 else None
    return {"schema": SCHEMA,
            "measured_s": round(measured_s, 6),
            "floor_s": round(f["floor_s"], 6),
            "ratio": round(ratio, 3) if ratio is not None else None,
            "phases": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in f.items()
                       if k != "floor_s"},
            "tokens": {"prompt": prompt_tokens, "completion": completion_tokens,
                       "batch": batch},
            "model": {"params": model.params, "weight_bytes": model.weight_bytes},
            "hardware": {"name": hw.name, "mem_bandwidth_gbs": hw.mem_bandwidth_gbs,
                         "peak_tflops": hw.peak_tflops, "rate_basis": hw.rate_basis,
                         "source": hw.source},
            "assumptions": ["weights read once per decode step and once for prefill",
                            "KV cache, activations and network time ignored",
                            "peak rates with full utilisation"],
            "does_not_prove": DOES_NOT_PROVE}


def summarize(receipts: list[dict]) -> dict:
    """Totals and the ratio spread over many receipts."""
    ratios = sorted(r["ratio"] for r in receipts if r["ratio"] is not None)
    measured = sum(r["measured_s"] for r in receipts)
    floor = sum(r["floor_s"] for r in receipts)

    def q(p: float):
        return ratios[min(len(ratios) - 1, int(p * len(ratios)))] if ratios else None
    return {"schema": SCHEMA + "#summary", "calls": len(receipts),
            "measured_s": round(measured, 3), "floor_s": round(floor, 3),
            "ratio_total": round(measured / floor, 3) if floor else None,
            "ratio_median": q(0.5), "ratio_p10": q(0.1), "ratio_p90": q(0.9),
            "below_floor": sum(1 for r in ratios if r < 1.0)}
