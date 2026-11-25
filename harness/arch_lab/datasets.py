"""Dataset loaders for DS-03 (286-formula physics) and DS-02 (BuildLang tasks).

Reads live workstation JSONL datasets when present and provides deterministic
stdlib fallback fixtures so offline CI runners execute identically.
Stdlib-only, <= 140 lines, every function <= 50 lines.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DS03_PATH = Path(r"H:\datasets\workstation-suite-2026-11-25\ds03\ds03_formulas_287.jsonl")
DEFAULT_DS02_PATH = Path(r"H:\datasets\workstation-suite-2026-11-25\ds02\ds02_buildlang_bench.jsonl")


@dataclass(frozen=True)
class RLTask:
    task_id: str
    dataset: str
    difficulty: int
    prompt: str
    params: dict[str, Any]
    oracle_kind: str  # "numeric_formula" | "buildlang_contract"
    expected_value: float | None = None
    rel_tol: float = 1e-9
    required_effects: tuple[str, ...] = ()
    mutated_value: float | None = None


def _fresnel_dielectric(n1: float, n2: float, cos_i: float) -> float:
    sin_i2 = max(0.0, 1.0 - cos_i * cos_i)
    sin_t2 = (n1 / n2) ** 2 * sin_i2
    if sin_t2 >= 1.0:
        return 1.0
    cos_t = math.sqrt(1.0 - sin_t2)
    rs = ((n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)) ** 2
    rp = ((n1 * cos_t - n2 * cos_i) / (n1 * cos_t + n2 * cos_i)) ** 2
    return 0.5 * (rs + rp)


def _srgb_to_linear(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _builtin_ds03_tasks() -> list[RLTask]:
    return [
        RLTask("OPT-002", "DS-03", 1, "Fresnel dielectric normal incidence n1=1.0, n2=1.5",
               {"n1": 1.0, "n2": 1.5, "cos_i": 1.0}, "numeric_formula",
               expected_value=_fresnel_dielectric(1.0, 1.5, 1.0), mutated_value=0.08),
        RLTask("OPT-004", "DS-03", 1, "Schlick reflectance f0=0.04, cos_theta=0.5",
               {"f0": 0.04, "cos_theta": 0.5}, "numeric_formula",
               expected_value=0.04 + 0.96 * (0.5 ** 5), mutated_value=0.04),
        RLTask("COL-001", "DS-03", 2, "sRGB to linear luminance v=0.5",
               {"v": 0.5}, "numeric_formula",
               expected_value=_srgb_to_linear(0.5), mutated_value=0.5 ** 2.2),
        RLTask("SIG-011", "DS-03", 2, "Ideal quantization SNR dB for 16 bits",
               {"bits": 16}, "numeric_formula",
               expected_value=6.020599913279624 * 16 + 1.7609125905568124, mutated_value=96.0),
        RLTask("PHY-054", "DS-03", 3, "Laplace spherical pressure gamma=0.072, r=0.001",
               {"gamma": 0.072, "r": 0.001}, "numeric_formula",
               expected_value=2.0 * 0.072 / 0.001, mutated_value=0.072 / 0.001),
    ]


def load_ds03_physics_tasks(path: Path | None = None) -> list[RLTask]:
    """Load DS-03 tasks anchored to live ds03_formulas_287.jsonl when available."""
    tasks = _builtin_ds03_tasks()
    src = path or DEFAULT_DS03_PATH
    if not src.is_file():
        return tasks
    indexed: dict[str, dict[str, Any]] = {}
    with src.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                row = json.loads(line)
                indexed[str(row.get("formula_id", ""))] = row
    enriched: list[RLTask] = []
    for t in tasks:
        row = indexed.get(t.task_id)
        if row:
            prompt = f"{t.task_id} ({row.get('name', t.prompt)}): {row.get('formula_expr', '')}"
            enriched.append(RLTask(**{**t.__dict__, "prompt": prompt}))
        else:
            enriched.append(t)
    return enriched


def load_ds02_buildlang_tasks(path: Path | None = None, limit: int = 3) -> list[RLTask]:
    """Load DS-02 BuildLang effect/contract tasks (live jsonl or deterministic fallback)."""
    src = path or DEFAULT_DS02_PATH
    tasks: list[RLTask] = []
    if src.is_file():
        with src.open("r", encoding="utf-8") as fh:
            for line in fh:
                if len(tasks) >= limit:
                    break
                row = json.loads(line)
                if row.get("expected_check_status") != "pass":
                    continue
                effects = tuple(str(e) for e in row.get("declared_effects", []))
                tasks.append(
                    RLTask(
                        task_id=str(row["task_id"]),
                        dataset="DS-02",
                        difficulty=2 + len(effects),
                        prompt=f"BuildLang module {row.get('rel_path', '')} passing check contract",
                        params={"rel_path": row.get("rel_path", ""), "loc": row.get("loc", 0)},
                        oracle_kind="buildlang_contract",
                        required_effects=effects,
                    )
                )
    if tasks:
        return tasks
    return [
        RLTask("ds02_pure_fnv", "DS-02", 2, "Pure BuildLang FNV-1a kernel with zero io effects",
               {"rel_path": "kcore/fnv1a.bld"}, "buildlang_contract", required_effects=()),
        RLTask("ds02_io_emit", "DS-02", 3, "BuildLang CLI emitting receipt with !io effect",
               {"rel_path": "workstation/receipt.bld"}, "buildlang_contract", required_effects=("io",)),
    ]
