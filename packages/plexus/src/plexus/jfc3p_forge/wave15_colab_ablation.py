"""Wave 15B Self-Contained Colab H100/A100/L4 & CPU Ablation Runner (A1..A4).

Executes all 4 Wave 15A ablations in pure Python 3.11+ stdlib (zero mandatory third-party deps):
- A1: JFC3P-7B-Oracle-v2 with exact 1-pass online-softmax Reverse-KL (m_q, l_q, m_p, l_p, S),
      Metamer-Split + RLVB (arXiv:2611.32884) belief-plate reward, and Arm C tool-loop scoring.
- A2: NOH-4 Reseating CODIT Valve vs NOH-3 permanent quarantine vs Flat baseline.
- A3: Plato-Key closed-form orthogonal Procrustes bridge (pure-stdlib Jacobi SVD + optional NumPy).
- A4: AVTR-4R multimodal 4-route gating + zero-FLOP video-still complexity pre-router.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import Any, Sequence

from .colab_h100_runner import build_forge_receipt, dense_exact_reverse_kl
from .fresco_molt_bridge import run_ablation_a5_fresco_molt
from .noh4_living_world import evaluate_noh4_vs_noh3_vs_flat
from .rtx4090_armc_eval import evaluate_armc_holdout
from .rtx4090_model_forge import adapt_colab_gpu_profile


def one_pass_online_reverse_kl(q_logits: Sequence[float], p_logits: Sequence[float], *, chunk_size: int = 32) -> float:
    """Exact 1-pass online-softmax Reverse-KL tracking 5 f64 scalars (m_q, l_q, m_p, l_p, S)."""
    n = len(q_logits)
    if n == 0 or n != len(p_logits) or chunk_size <= 0:
        raise ValueError("invalid logits or chunk_size for one_pass_online_reverse_kl")
    m_q = m_p = -math.inf
    l_q = l_p = s_acc = 0.0
    for start in range(0, n, chunk_size):
        qc = q_logits[start : start + chunk_size]
        pc = p_logits[start : start + chunk_size]
        mq_new = max(m_q, max(qc))
        mp_new = max(m_p, max(pc))
        rq = math.exp(m_q - mq_new) if math.isfinite(m_q) else 0.0
        rp = math.exp(m_p - mp_new) if math.isfinite(m_p) else 0.0
        eq = [math.exp(v - mq_new) for v in qc]
        ep = [math.exp(v - mp_new) for v in pc]
        l_q = l_q * rq + sum(eq)
        l_p = l_p * rp + sum(ep)
        s_acc = s_acc * rq + sum(e_val * (qv - pv) for e_val, qv, pv in zip(eq, qc, pc))
        m_q, m_p = mq_new, mp_new
    lse_q = m_q + math.log(l_q)
    lse_p = m_p + math.log(l_p)
    return max(0.0, (s_acc / l_q) - (lse_q - lse_p))


@dataclass(frozen=True)
class MetamerPair:
    pair_id: str
    prompt_a: str
    prompt_b: str
    answer_a: str
    answer_b: str


class MetamerSplitRewardScorer:
    """Joint near-metamer twin scorer + RLVB (arXiv:2611.32884) open-belief commit guard."""

    def score_pair(
        self, pair: MetamerPair, pred_a: str, pred_b: str, *,
        belief_open_a: bool = False, belief_open_b: bool = False,
    ) -> dict[str, Any]:
        ok_a = pred_a.strip() == pair.answer_a.strip() and not belief_open_a
        ok_b = pred_b.strip() == pair.answer_b.strip() and not belief_open_b
        collapsed = pred_a.strip() == pred_b.strip() and pair.answer_a.strip() != pair.answer_b.strip()
        return {"pair_id": pair.pair_id, "ok_a": ok_a, "ok_b": ok_b, "surface_collapsed": collapsed, "reward": 1.0 if (ok_a and ok_b) else 0.0}

    def evaluate_batch(
        self, pairs: Sequence[MetamerPair], preds: Sequence[tuple[str, str]],
        belief_flags: Sequence[tuple[bool, bool]] | None = None,
    ) -> dict[str, Any]:
        flags = list(belief_flags) if belief_flags is not None else [(False, False)] * len(pairs)
        rows = [self.score_pair(p, pa, pb, belief_open_a=fa, belief_open_b=fb) for p, (pa, pb), (fa, fb) in zip(pairs, preds, flags)]
        n = max(1, len(rows))
        return {
            "mean_reward": round(sum(r["reward"] for r in rows) / n, 6),
            "surface_collapse_rate": round(sum(1 for r in rows if r["surface_collapsed"]) / n, 6),
            "details": rows,
        }


def _mat_mul(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> list[list[float]]:
    rows, inner, cols = len(a), len(b), len(b[0])
    return [[sum(a[i][k] * b[k][j] for k in range(inner)) for j in range(cols)] for i in range(rows)]


def _mat_T(a: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[a[r][c] for r in range(len(a))] for c in range(len(a[0]))]


def _jacobi_sym_eig(sym: list[list[float]], max_sweeps: int = 40) -> tuple[list[float], list[list[float]]]:
    n = len(sym)
    a = [list(row) for row in sym]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off = 0.0
        for p in range(n):
            for q in range(p + 1, n):
                apq = a[p][q]
                off += apq * apq
                if abs(apq) < 1e-15:
                    continue
                tau = (a[q][q] - a[p][p]) / (2.0 * apq)
                t = math.copysign(1.0 / (abs(tau) + math.sqrt(1.0 + tau * tau)), tau)
                c = 1.0 / math.sqrt(1.0 + t * t)
                s = t * c
                a[p][p] -= t * apq
                a[q][q] += t * apq
                a[p][q] = a[q][p] = 0.0
                for k in range(n):
                    if k != p and k != q:
                        akp, akq = a[k][p], a[k][q]
                        a[k][p] = a[p][k] = c * akp - s * akq
                        a[k][q] = a[q][k] = s * akp + c * akq
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
        if off < 1e-26:
            break
    return [a[i][i] for i in range(n)], v


class PlatoKeyProcrustesBridge:
    """Closed-form zero-gradient orthogonal Procrustes + global scale latent bridge (pure stdlib)."""

    def __init__(self) -> None:
        self.rotation: list[list[float]] | None = None
        self.scale: float = 1.0

    def fit(self, src_states: Sequence[Sequence[float]], dst_states: Sequence[Sequence[float]]) -> dict[str, float]:
        x = [[float(v) for v in row] for row in src_states]
        y = [[float(v) for v in row] for row in dst_states]
        m_mat = _mat_mul(_mat_T(y), x)
        eigvals, v_mat = _jacobi_sym_eig(_mat_mul(_mat_T(m_mat), m_mat))
        d = len(eigvals)
        mv = _mat_mul(m_mat, v_mat)
        u_cols: list[list[float]] = []
        for k in range(d):
            sigma = math.sqrt(max(eigvals[k], 0.0))
            col = [mv[r][k] / sigma for r in range(d)] if sigma > 1e-12 else [1.0 if r == k else 0.0 for r in range(d)]
            u_cols.append(col)
        u_mat = _mat_T(u_cols)
        r_mat = _mat_mul(u_mat, _mat_T(v_mat))
        xr = _mat_mul(x, _mat_T(r_mat))
        num = sum(xr[i][j] * y[i][j] for i in range(len(x)) for j in range(d))
        den = max(sum(x[i][j] * x[i][j] for i in range(len(x)) for j in range(d)), 1e-15)
        self.rotation, self.scale = r_mat, num / den
        pred = self.transform(x)
        rtr = _mat_mul(_mat_T(r_mat), r_mat)
        ortho_err = max(abs(rtr[i][j] - (1.0 if i == j else 0.0)) for i in range(d) for j in range(d))
        max_abs_err = max(abs(pred[i][j] - y[i][j]) for i in range(len(x)) for j in range(d))
        return {"max_abs_err": max_abs_err, "ortho_err": ortho_err, "scale": round(self.scale, 6)}

    def transform(self, src_states: Sequence[Sequence[float]]) -> list[list[float]]:
        if self.rotation is None:
            raise RuntimeError("Call fit() before transform()")
        xr = _mat_mul([[float(v) for v in row] for row in src_states], _mat_T(self.rotation))
        return [[self.scale * v for v in row] for row in xr]


class AVTR4RouteController:
    """Deterministic 4-route AVTR controller + RLVB escalation + zero-FLOP video-still pre-router."""

    ROUTE_TOKENS: dict[str, int] = {"<direct>": 48, "<imagine>": 160, "<think>": 380, "<imagine_then_think>": 520}

    def __init__(self, vis_thresh: float = 0.45, txt_thresh: float = 0.50, belief_thresh: float = 0.40) -> None:
        self.vis_thresh, self.txt_thresh, self.belief_thresh = vis_thresh, txt_thresh, belief_thresh

    @staticmethod
    def visual_complexity_from_still_stats(scene_cuts: int, motion_peak: float, edge_density: float) -> float:
        return min(1.0, 0.35 * min(scene_cuts / 4.0, 1.0) + 0.35 * min(motion_peak / 30.0, 1.0) + 0.30 * min(edge_density / 1500.0, 1.0))

    def route(self, visual_complexity: float, text_depth: float, belief_ambiguity: float = 0.0) -> dict[str, Any]:
        need_vis, need_txt = visual_complexity >= self.vis_thresh, text_depth >= self.txt_thresh
        wait_rlvb = belief_ambiguity >= self.belief_thresh
        if need_vis and (need_txt or wait_rlvb):
            tag = "<imagine_then_think>"
        elif need_vis:
            tag = "<imagine>"
        elif need_txt or wait_rlvb:
            tag = "<think>"
        else:
            tag = "<direct>"
        return {"route": tag, "est_tokens": self.ROUTE_TOKENS[tag], "always_think_tokens": 520, "rlvb_wait_triggered": wait_rlvb}


def run_ablation_a1_metamer_rlvb_armc() -> dict[str, Any]:
    rng = random.Random(15)
    q = [rng.uniform(-3.0, 3.0) for _ in range(512)]
    p = [rng.uniform(-3.0, 3.0) for _ in range(512)]
    dense_kl = dense_exact_reverse_kl(q, p)
    one_pass_kl = one_pass_online_reverse_kl(q, p, chunk_size=37)
    kl_err = abs(dense_kl - one_pass_kl)
    scorer = MetamerSplitRewardScorer()
    pairs = [MetamerPair("M1", "+9.81 * 2", "-9.81 * 2", "19.62", "-19.62"), MetamerPair("M2", "10 m to cm", "10 cm to m", "1000", "0.1")]
    dummy = scorer.evaluate_batch(pairs, [("19.62", "19.62"), ("1000", "1000")])
    solver = scorer.evaluate_batch(pairs, [("19.62", "-19.62"), ("1000", "0.1")])
    open_rlvb = scorer.score_pair(pairs[0], "19.62", "-19.62", belief_open_a=True)
    armc_items = [{"id": "A1-F64", "eval_type": "numeric_f64_oracle", "prompt": "Hohmann LEO->GEO", "expected_value": 3.892607743591, "rel_tol": 1e-6, "abs_tol": 1e-9}]
    armc = evaluate_armc_holdout(
        armc_items,
        lambda msgs: {"text": msgs[-1]["content"] if "[ORACLE_RESULT]" in msgs[-1]["content"] else "<think>call:f64_oracle(hohmann, r1=6678, r2=42164)</think>", "tokens": 18, "elapsed_s": 0.01},
    )
    ok = kl_err < 1e-12 and dummy["mean_reward"] == 0.0 and solver["mean_reward"] == 1.0 and open_rlvb["reward"] == 0.0 and armc["armc_passed"] == 1
    return {
        "ok": ok, "one_pass_kl_abs_err": kl_err, "dummy_reward": dummy["mean_reward"],
        "dummy_collapse_rate": dummy["surface_collapse_rate"], "solver_reward": solver["mean_reward"],
        "rlvb_open_commit_reward": open_rlvb["reward"], "armc_raw_vs_tool": {"raw": armc["raw_passed"], "armc": armc["armc_passed"]},
    }


def run_ablation_a3_plato_key() -> dict[str, Any]:
    rng = random.Random(7)
    d = 6
    x = [[rng.gauss(0.0, 1.0) for _ in range(d)] for _ in range(28)]
    # Construct exact orthogonal rotation matrix via product of Givens rotations.
    rot = [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]
    for idx, angle in enumerate((0.4, -0.7, 1.1, 0.3, -0.9)):
        g = [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]
        c, s = math.cos(angle), math.sin(angle)
        g[idx][idx], g[idx][idx + 1], g[idx + 1][idx], g[idx + 1][idx + 1] = c, -s, s, c
        rot = _mat_mul(rot, g)
    y = [[1.75 * v for v in row] for row in _mat_mul(x, _mat_T(rot))]
    fit = PlatoKeyProcrustesBridge().fit(x, y)
    # Planted non-orthogonal shear distortion must yield high residual error.
    y_shear = [[row[0] * 3.0 + row[1] * 2.5, *row[1:]] for row in y]
    shear_fit = PlatoKeyProcrustesBridge().fit(x, y_shear)
    ok = fit["max_abs_err"] < 1e-11 and fit["ortho_err"] < 1e-11 and shear_fit["max_abs_err"] > 0.5
    return {"ok": ok, "exact_rotation": fit, "planted_shear_max_abs_err": round(shear_fit["max_abs_err"], 6)}


def run_ablation_a4_avtr_4r() -> dict[str, Any]:
    ctrl = AVTR4RouteController()
    still_hi = ctrl.visual_complexity_from_still_stats(scene_cuts=4, motion_peak=28.0, edge_density=1400.0)
    still_lo = ctrl.visual_complexity_from_still_stats(scene_cuts=0, motion_peak=2.0, edge_density=150.0)
    workloads = [(still_lo, 0.1, 0.0), (still_hi, 0.2, 0.1), (still_lo, 0.8, 0.1), (still_hi, 0.9, 0.6)]
    routed = [ctrl.route(*w) for w in workloads]
    saved = 1.0 - sum(r["est_tokens"] for r in routed) / float(sum(r["always_think_tokens"] for r in routed))
    routes = [r["route"] for r in routed]
    ok = routes == ["<direct>", "<imagine>", "<think>", "<imagine_then_think>"] and saved > 0.40 and routed[3]["rlvb_wait_triggered"]
    return {"ok": ok, "routes": routes, "token_reduction_frac": round(saved, 4), "still_hi": round(still_hi, 4), "still_lo": round(still_lo, 4)}


def run_wave15_colab_ablations(*, ablation: str = "all", gpu_name: str = "L4", out_dir: Path | None = None) -> dict[str, Any]:
    """Run selected Wave 15A/15B/21B ablations (A1..A5 or all) and emit canonical engine-receipt/1."""
    selected = ("A1", "A2", "A3", "A4", "A5") if ablation == "all" else (ablation,)
    runners = {
        "A1": run_ablation_a1_metamer_rlvb_armc, "A2": evaluate_noh4_vs_noh3_vs_flat,
        "A3": run_ablation_a3_plato_key, "A4": run_ablation_a4_avtr_4r, "A5": run_ablation_a5_fresco_molt,
    }
    results = {key: runners[key]() for key in selected}
    ok = all(bool(r["ok"]) for r in results.values())
    payload: dict[str, Any] = {"ok": ok, "ablation": ablation, "gpu_config": adapt_colab_gpu_profile(gpu_name), "results": results}
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "wave15_ablation_summary.json"
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        rec = build_forge_receipt(
            task_id=f"wave15b-ablation-{ablation}", artifact_paths=[p],
            oracle_exit_code=0 if ok else 1,
            oracle_stdout="[PASS] wave15 colab ablations verified\n" if ok else "[FAIL] wave15 ablation failed\n",
            oracle_command=["python", "-m", "plexus.jfc3p_forge.wave15_colab_ablation", "--ablation", ablation], root=out_dir,
        )
        (out_dir / "engine_receipt.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["receipt_envelope_sha256"] = rec["digests"]["envelope_sha256"]
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave 15B/21B Colab H100/A100/L4 & CPU Ablation Runner")
    parser.add_argument("--ablation", choices=("all", "A1", "A2", "A3", "A4", "A5"), default="all")
    parser.add_argument("--gpu", default="L4")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    res = run_wave15_colab_ablations(ablation=args.ablation, gpu_name=args.gpu, out_dir=args.out)
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
