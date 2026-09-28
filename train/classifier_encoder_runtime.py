"""Runtime scoring for the optional neural classifier encoder."""
from __future__ import annotations

from collections import OrderedDict
from time import perf_counter
from typing import Any

from harness.decision_contract import validate_request
from harness.evidence_json import canonical_sha256

from .classifier_encoder import ABSTAIN_ID, SCORE_SCHEMA, EncoderClassifierError


class EncoderClassifierRuntime:
    """Shared-text batch scorer with a bounded model-bound embedding cache."""

    def __init__(self, model: Any, tokenizer: Any, artifact_identity: str,
                 *, cache_size: int = 4096, encode_batch_size: int = 32,
                 device: str = "cpu") -> None:
        if not isinstance(artifact_identity, str) or not artifact_identity:
            raise EncoderClassifierError("invalid artifact identity")
        if not isinstance(cache_size, int) or not 0 <= cache_size <= 100_000:
            raise EncoderClassifierError("invalid cache size")
        if not isinstance(encode_batch_size, int) or not 1 <= encode_batch_size <= 512:
            raise EncoderClassifierError("invalid encode batch size")
        self.model = model.to(device)
        self.model.eval()
        self.tokenizer = tokenizer
        self.artifact_identity = artifact_identity
        self.cache_size = cache_size
        self.encode_batch_size = encode_batch_size
        self.device = device
        self._cache: OrderedDict[tuple[str, str], Any] = OrderedDict()

    def clear_cache(self) -> None:
        self._cache.clear()

    def set_model(self, model: Any, artifact_identity: str) -> None:
        self.clear_cache()
        self.model = model.to(self.device)
        self.model.eval()
        self.artifact_identity = artifact_identity

    def _cache_get(self, text: str, stats: dict) -> Any | None:
        key = (self.artifact_identity, text)
        if key not in self._cache:
            stats["misses"] += 1
            return None
        stats["hits"] += 1
        value = self._cache.pop(key)
        self._cache[key] = value
        return value

    def _cache_put(self, text: str, value: Any) -> None:
        if not self.cache_size:
            return
        key = (self.artifact_identity, text)
        self._cache[key] = value.detach().cpu()
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _embeddings(self, texts: list[str], stats: dict) -> dict[str, Any]:
        torch = __import__("torch")
        out, misses = {}, []
        for text in texts:
            cached = self._cache_get(text, stats)
            if cached is None:
                misses.append(text)
            else:
                out[text] = cached.to(self.device)
        if misses:
            unique = list(dict.fromkeys(misses))
            for start in range(0, len(unique), self.encode_batch_size):
                chunk = unique[start:start + self.encode_batch_size]
                with torch.no_grad():
                    reps = self.model.encode_texts(self.tokenizer, chunk, device=self.device)
                for text, rep in zip(chunk, reps):
                    self._cache_put(text, rep)
                    out[text] = rep.detach()
        return out

    def _sync(self) -> None:
        torch = __import__("torch")
        if str(self.device).startswith("cuda") and torch.cuda.is_available():
            torch.cuda.synchronize()

    def score_batch(self, requests: list[dict], *, task_family: str) -> list[dict]:
        if not isinstance(requests, list) or len(requests) > 10_000:
            raise EncoderClassifierError("requests must be a bounded list")
        if not isinstance(task_family, str) or not task_family:
            raise EncoderClassifierError("invalid task family")
        torch = __import__("torch")
        total_start = perf_counter()
        snapshots = [validate_request(item) for item in requests]
        stats = {"hits": 0, "misses": 0}
        texts = []
        for request in snapshots:
            texts.append(request["state"])
            texts.extend(choice["description"] for choice in request["choices"])
        embeddings = self._embeddings(list(dict.fromkeys(texts)), stats)
        self._sync()
        envelopes = []
        for request in snapshots:
            head_start = perf_counter()
            choice_ids = [choice["id"] for choice in request["choices"]]
            eligible = set(request["eligible_choice_ids"])
            query = embeddings[request["state"]].to(self.device)
            candidate_reps = torch.stack([
                embeddings[choice["description"]].to(self.device)
                for choice in request["choices"]
            ])
            eligible_indexes = [idx for idx, cid in enumerate(choice_ids) if cid in eligible]
            if eligible_indexes:
                cand_logits = self.model.score_embeddings(
                    task_family, query, candidate_reps[eligible_indexes])
            else:
                cand_logits = torch.empty(0, device=query.device)
            abstain = self.model.abstain_logit(task_family, query).reshape(1)
            all_logits = torch.cat([cand_logits, abstain]).double()
            probs = torch.softmax(all_logits, dim=0).detach().cpu()
            scores, cursor = [], 0
            for idx, choice in enumerate(request["choices"]):
                if idx not in eligible_indexes:
                    scores.append({
                        "choice_id": choice["id"], "eligible": False,
                        "raw_logit": None, "probability_like": 0.0,
                    })
                    continue
                scores.append({
                    "choice_id": choice["id"], "eligible": True,
                    "raw_logit": float(cand_logits[cursor].detach().cpu()),
                    "probability_like": float(probs[cursor]),
                })
                cursor += 1
            scores.append({
                "choice_id": ABSTAIN_ID, "eligible": True,
                "raw_logit": float(abstain[0].detach().cpu()),
                "probability_like": float(probs[-1]),
            })
            envelopes.append({
                "schema": SCORE_SCHEMA,
                "model_ref": self.artifact_identity,
                "task_family": task_family,
                "request_sha256": canonical_sha256(request),
                "candidate_ids": choice_ids + [ABSTAIN_ID],
                "eligible_candidate_ids": list(request["eligible_choice_ids"]) + [ABSTAIN_ID],
                "scores": scores,
                "head_scoring_latency_ms": round((perf_counter() - head_start) * 1000, 3),
                "encoder_cache": dict(stats),
                "calibration": {
                    "status": "uncalibrated",
                    "probability_semantics": "raw_softmax_like_not_calibrated",
                },
                "selection": {
                    "automatic_selection_enabled": False,
                    "reason": "uncalibrated_neural_scores",
                },
                "does_not_prove": [
                    "calibrated probability, label truth, or held-out workflow quality",
                    "authorization, execution safety, semantic correctness, or verifier acceptance",
                ],
            })
        self._sync()
        total_ms = round((perf_counter() - total_start) * 1000, 3)
        amortized = round(total_ms / len(envelopes), 3) if envelopes else 0.0
        for envelope in envelopes:
            envelope["batch_size"] = len(envelopes)
            envelope["batch_scoring_latency_ms"] = total_ms
            envelope["amortized_batch_latency_ms"] = amortized
        return envelopes
