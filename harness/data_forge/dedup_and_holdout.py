"""Stage 2 three-tier deduplication and Stage 3 zero-leak holdout decontamination."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from .common import extract_code_snippet, extract_row_text, normalized_ast_hash, word_tokens

_MINHASH_SALTS: tuple[int, ...] = (
    0x9E3779B185EBCA87, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9, 0x85EBCA77C2B2AE63,
    0x27D4EB2F165667C5, 0x94D049BB133111EB, 0xBF58476D1CE4E5B9, 0xD6E8FEB86659FD93,
)


def _shingle_hashes(tokens: Sequence[str]) -> list[int]:
    n = len(tokens)
    if n < 3:
        shingles = [" ".join(tokens)] if tokens else []
    else:
        shingles = [f"{tokens[i]} {tokens[i + 1]} {tokens[i + 2]}" for i in range(n - 2)]
    return [int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little") for s in shingles]


def compute_simhash64(sh_hashes: Sequence[int]) -> int:
    """Fast 64-bit Charikar SimHash over pre-hashed 3-word shingles."""
    if not sh_hashes:
        return 0
    weights = [0] * 64
    for h in sh_hashes:
        for bit in range(64):
            if (h >> bit) & 1:
                weights[bit] += 1
            else:
                weights[bit] -= 1
    out = 0
    for bit in range(64):
        if weights[bit] > 0:
            out |= 1 << bit
    return out


def compute_minhash8(sh_hashes: Sequence[int]) -> tuple[int, ...]:
    """8-permutation MinHash signature over pre-hashed 3-word shingles."""
    if not sh_hashes:
        return (0,) * 8
    mask = (1 << 64) - 1
    return tuple(min(((h ^ salt) * 0xBF58476D1CE4E5B9) & mask for h in sh_hashes) for salt in _MINHASH_SALTS)


class ThreeTierDeduplicator:
    """Exact SHA-256 + SimHash/MinHash LSH near-duplicate clustering + AST structural dedup."""

    def __init__(self, max_hamming: int = 3, jaccard_threshold: float = 0.72, min_tokens: int = 10) -> None:
        self.max_hamming = max_hamming
        self.jaccard_threshold = jaccard_threshold
        self.min_tokens = min_tokens
        self.exact_hashes: set[str] = set()
        self.ast_hashes: set[str] = set()
        self.sim_bands: tuple[dict[int, list[int]], ...] = tuple(defaultdict(list) for _ in range(4))
        self.mh_bands: tuple[dict[tuple[int, int], list[int]], ...] = tuple(defaultdict(list) for _ in range(4))
        self.simhashes: list[int] = []
        self.shingle_sets: list[frozenset[int]] = []
        self.stats: Counter[str] = Counter()

    def check_and_add(self, text: str, tokens: Sequence[str], code: str) -> tuple[bool, str]:
        """Accept unseen content or fail-closed with the duplicate tier reason."""
        del text
        norm = " ".join(tokens)
        exact = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        if exact in self.exact_hashes:
            self.stats["exact_dup"] += 1
            return False, "EXACT_SHA256_DUPLICATE"

        ast_h = normalized_ast_hash(code) if code else None
        if ast_h is not None and ast_h in self.ast_hashes:
            self.stats["ast_dup"] += 1
            return False, "AST_STRUCTURAL_DUPLICATE"

        sh_hashes = _shingle_hashes(tokens) if len(tokens) >= self.min_tokens else []
        sh: int | None = None
        mh: tuple[int, ...] | None = None
        sh_set: frozenset[int] = frozenset(sh_hashes)
        if sh_hashes:
            sh = compute_simhash64(sh_hashes)
            mh = compute_minhash8(sh_hashes)
            checked_sim: set[int] = set()
            for band_idx in range(4):
                band_key = (sh >> (band_idx * 16)) & 0xFFFF
                for cand_id in self.sim_bands[band_idx].get(band_key, ()):
                    if cand_id in checked_sim:
                        continue
                    checked_sim.add(cand_id)
                    if (sh ^ self.simhashes[cand_id]).bit_count() <= self.max_hamming:
                        self.stats["simhash_near_dup"] += 1
                        return False, "NEAR_DUPLICATE_SIMHASH"
            checked_mh: set[int] = set()
            for band_idx in range(4):
                mh_key = (mh[band_idx * 2], mh[band_idx * 2 + 1])
                for cand_id in self.mh_bands[band_idx].get(mh_key, ()):
                    if cand_id in checked_mh:
                        continue
                    checked_mh.add(cand_id)
                    other = self.shingle_sets[cand_id]
                    union_n = len(sh_set | other)
                    if union_n > 0 and (len(sh_set & other) / union_n) >= self.jaccard_threshold:
                        self.stats["minhash_near_dup"] += 1
                        return False, "NEAR_DUPLICATE_MINHASH"

        self.exact_hashes.add(exact)
        if ast_h is not None:
            self.ast_hashes.add(ast_h)
        if sh is not None and mh is not None:
            row_idx = len(self.simhashes)
            self.simhashes.append(sh)
            self.shingle_sets.append(sh_set)
            for band_idx in range(4):
                self.sim_bands[band_idx][(sh >> (band_idx * 16)) & 0xFFFF].append(row_idx)
                self.mh_bands[band_idx][(mh[band_idx * 2], mh[band_idx * 2 + 1])].append(row_idx)
        return True, "OK"


class HoldoutDecontaminator:
    """Blocks exact, 13-gram, multi-8-gram, and normalized AST overlap against sealed holdouts."""

    def __init__(self, holdout_rows: Sequence[dict[str, Any]]) -> None:
        self.exact_hashes: set[str] = set()
        self.grams13: set[str] = set()
        self.grams8: set[str] = set()
        self.ast_hashes: set[str] = set()
        self.holdout_count = 0

        for row in holdout_rows:
            self.holdout_count += 1
            text = extract_row_text(row)
            toks = word_tokens(text)
            if toks:
                self.exact_hashes.add(hashlib.sha256(" ".join(toks).encode("utf-8")).hexdigest())
                for i in range(max(0, len(toks) - 12)):
                    self.grams13.add(" ".join(toks[i : i + 13]))
                for i in range(max(0, len(toks) - 7)):
                    self.grams8.add(" ".join(toks[i : i + 8]))
            code = extract_code_snippet(row, text)
            if code:
                ah = normalized_ast_hash(code)
                if ah is not None:
                    self.ast_hashes.add(ah)

    def is_clean(self, tokens: Sequence[str], code: str) -> tuple[bool, str]:
        """Verify candidate tokens and code have zero overlap with indexed holdouts."""
        if not self.holdout_count:
            return True, "OK"
        if tokens:
            eh = hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()
            if eh in self.exact_hashes:
                return False, "HOLDOUT_CONTAMINATION:EXACT"
            for i in range(max(0, len(tokens) - 12)):
                if " ".join(tokens[i : i + 13]) in self.grams13:
                    return False, "HOLDOUT_CONTAMINATION:13GRAM"
            hits8 = 0
            for i in range(max(0, len(tokens) - 7)):
                if " ".join(tokens[i : i + 8]) in self.grams8:
                    hits8 += 1
                    if hits8 >= 2:
                        return False, "HOLDOUT_CONTAMINATION:8GRAM"
        if code:
            ah = normalized_ast_hash(code)
            if ah is not None and ah in self.ast_hashes:
                return False, "HOLDOUT_CONTAMINATION:AST"
        return True, "OK"
