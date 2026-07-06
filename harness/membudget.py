"""membudget.py — the memory subsystem's planning core (M5/MEM-LAYER).

Models QLoRA VRAM breakdown and recommends the config that fits a target card.
This is the democratization decision layer: "can model X run on card Y, and
how?" It answers before you spend hours on a run that OOMs.

The constants are CALIBRATED ESTIMATES (±20%) derived from observed smokes:
  - 14B @ seq_len 2048, r16 all-targets, grad-ckpt: observed peak 21.04 GB (fits 24)
  - 32B @ seq_len 2048: OOMs in backward (>24 GB)
The falsifier checks FIT-DECISIONS against these observations, not exact GB
(the exact peak depends on fragmentation/allocator behavior the model can't
predict). Honest about its tolerance.

Dominant terms:
  - 4-bit weights (nf4 + double-quant + per-group metadata): params * ~0.63 B/param
  - fp32 embedding head (if prepare_model_for_kbit_training upcasts): vocab*hidden*4
  - LoRA trainable: trainable * 8 B (fp32 weights + fp32 grads)
  - optimizer (paged_adamw_8bit): trainable * ~1 B resident (rest paged to CPU)
  - activation peak (grad-ckpt, one recomputed segment): seq_len*layers*hidden*k
  - fixed overhead (cuda ctx, fragmentation, buffers): ~2.5 GB
"""
from __future__ import annotations
from dataclasses import dataclass

GB = 1024 ** 3
W_4BIT_BYTES_PER_PARAM = 0.63
ACTIVATION_K = 16.0
FIXED_OVERHEAD_GB = 2.5
SAFETY_MARGIN_GB = 0.5


@dataclass
class ModelProfile:
    name: str
    params_b: float
    hidden: int
    layers: int
    vocab: int


@dataclass
class VRAMBreakdown:
    weights_4bit_gb: float
    embedding_fp32_gb: float
    lora_gb: float
    optimizer_gb: float
    activations_gb: float
    overhead_gb: float
    total_gb: float
    target_gb: float

    @property
    def fits(self) -> bool:
        return self.total_gb <= self.target_gb - SAFETY_MARGIN_GB

    @property
    def headroom_gb(self) -> float:
        return self.target_gb - self.total_gb


def estimate_vram(model: ModelProfile, *, seq_len: int, lora_trainable: int,
                  upcast_fp32: bool = False,
                  target_gb: float = 24.0) -> VRAMBreakdown:
    w = model.params_b * 1e9 * W_4BIT_BYTES_PER_PARAM / GB
    emb = (model.vocab * model.hidden * 4 / GB) if upcast_fp32 else 0.0
    lora = lora_trainable * 8 / GB
    opt = lora_trainable * 1 / GB
    act = seq_len * model.layers * model.hidden * ACTIVATION_K / GB
    oh = FIXED_OVERHEAD_GB
    total = w + emb + lora + opt + act + oh
    return VRAMBreakdown(w, emb, lora, opt, act, oh, total, target_gb)


@dataclass
class Recommendation:
    fits_native: bool
    max_seq_len_native: int
    needs_offload: bool
    needs_lower_seqlen: bool
    offload_strategy: str
    note: str


def recommend(model: ModelProfile, *, target_gb: float = 24.0,
              lora_trainable: int = 70_000_000,
              want_seq_len: int = 2048,
              upcast_fp32: bool = False) -> Recommendation:
    sl = want_seq_len
    while sl >= 128:
        if estimate_vram(model, seq_len=sl, lora_trainable=lora_trainable,
                         upcast_fp32=upcast_fp32, target_gb=target_gb).fits:
            return Recommendation(
                fits_native=(sl >= want_seq_len),
                max_seq_len_native=sl, needs_offload=(sl < want_seq_len),
                needs_lower_seqlen=(sl < want_seq_len),
                offload_strategy="none" if sl >= want_seq_len
                    else f"lower seq_len to {sl} OR activation-CPU-offload to keep {want_seq_len}",
                note=f"{model.name}: fits {target_gb:.0f}GB at seq_len {sl} native")
        sl = sl // 2
    return Recommendation(
        fits_native=False, max_seq_len_native=0, needs_offload=True,
        needs_lower_seqlen=True,
        offload_strategy="weight-CPU-offload (ZeRO-3) required — weights exceed card even at min seq_len",
        note=f"{model.name}: 4-bit weights alone exceed {target_gb:.0f}GB budget")


QWEN_14B = ModelProfile("Qwen2.5-Coder-14B", 14.8, 5120, 48, 152064)
QWEN_32B = ModelProfile("Qwen2.5-Coder-32B", 32.8, 5120, 64, 152064)
RTX_4090_GB = 24.0
