"""membudget falsifier — the planner must retrodict OBSERVED fit-decisions.

Two ground-truth data points from this session's smokes:
  - 14B @ seq_len 2048, r16 all-targets, grad-ckpt: observed peak 21.04 GB → FITS 24 GB.
  - 32B @ seq_len 2048: OOMs in backward → DOES NOT FIT 24 GB.

The model is a calibrated estimate (±~20% on exact GB). The falsifier checks
the BINARY fit-decision against these observations (robust to calibration error)
plus the recommender's strategy output, NOT the exact GB number.
"""
import pytest

from harness.membudget import (estimate_vram, recommend, QWEN_14B, QWEN_32B,
                               RTX_4090_GB)


def test_14b_fits_24gb_at_seq_len_2048():
    """Retrodicts the observed 14B smoke (21.04 GB peak, fits 24)."""
    b = estimate_vram(QWEN_14B, seq_len=2048, lora_trainable=70_000_000,
                      target_gb=RTX_4090_GB)
    assert b.fits, f"14B must fit 24GB at 2048 (model says {b.total_gb:.1f}GB)"


def test_32b_does_not_fit_24gb_at_seq_len_2048():
    """Retrodicts the observed 32B OOM."""
    b = estimate_vram(QWEN_32B, seq_len=2048, lora_trainable=134_000_000,
                      target_gb=RTX_4090_GB)
    assert not b.fits, f"32B must NOT fit 24GB at 2048 (model says {b.total_gb:.1f}GB)"


def test_weights_dominate_32b_budget():
    """For the 32B, 4-bit weights are the dominant term (>55% of total)."""
    b = estimate_vram(QWEN_32B, seq_len=2048, lora_trainable=134_000_000,
                      target_gb=RTX_4090_GB)
    assert b.weights_4bit_gb / b.total_gb > 0.55


def test_recommend_14b_fits_native():
    r = recommend(QWEN_14B, target_gb=RTX_4090_GB, want_seq_len=2048,
                  lora_trainable=70_000_000)
    assert r.fits_native
    assert r.max_seq_len_native >= 2048
    assert not r.needs_offload


def test_recommend_32b_needs_offload():
    r = recommend(QWEN_32B, target_gb=RTX_4090_GB, want_seq_len=2048,
                  lora_trainable=134_000_000)
    assert r.needs_offload
    assert r.max_seq_len_native < 2048
    assert "offload" in r.offload_strategy.lower() or "lower" in r.offload_strategy.lower()


def test_smaller_card_pushes_14b_to_offload():
    """A 16 GB card (e.g. 4080/5070) can't fit the 14B at 2048 native."""
    r = recommend(QWEN_14B, target_gb=16.0, want_seq_len=2048,
                  lora_trainable=70_000_000)
    assert r.needs_offload or r.max_seq_len_native < 2048


def test_estimate_is_deterministic():
    a = estimate_vram(QWEN_14B, seq_len=2048, lora_trainable=70_000_000)
    b = estimate_vram(QWEN_14B, seq_len=2048, lora_trainable=70_000_000)
    assert a.total_gb == b.total_gb


def test_halving_seqlen_halves_activations():
    full = estimate_vram(QWEN_32B, seq_len=2048, lora_trainable=134_000_000)
    half = estimate_vram(QWEN_32B, seq_len=1024, lora_trainable=134_000_000)
    assert abs(half.activations_gb - full.activations_gb / 2) < 0.01
