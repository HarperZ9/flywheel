"""Optional neural encoder candidate classifier training."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Callable

from harness.classifier_dataset import validate_example

from .classifier_encoder_report import build_training_report

ABSTAIN_ID = "__abstain__"
SCORE_SCHEMA = "flywheel.classifier-encoder-score-envelope/v1"


class EncoderClassifierError(ValueError):
    """Neural classifier input, model, or artifact failed closed."""


@dataclass(frozen=True)
class EncoderTrainConfig:
    seed: int = 0
    epochs: int = 3
    learning_rate: float = 2e-5
    head_learning_rate: float = 1e-3
    batch_size: int = 4
    max_steps: int | None = None
    max_length: int = 256
    device: str = "cpu"
    fine_tune_last_n_layers: int = 0
    progress_every: int = 0


@dataclass
class EncoderTrainingResult:
    model: Any
    tokenizer: Any
    report: dict


def _torch():
    try:
        import torch
    except ImportError as exc:
        raise EncoderClassifierError("torch is required for classifier encoder") from exc
    return torch


def _check_config(config: EncoderTrainConfig) -> None:
    if not isinstance(config.seed, int):
        raise EncoderClassifierError("invalid seed")
    if not isinstance(config.epochs, int) or not 1 <= config.epochs <= 1000:
        raise EncoderClassifierError("invalid epoch count")
    if not isinstance(config.batch_size, int) or not 1 <= config.batch_size <= 256:
        raise EncoderClassifierError("invalid batch size")
    if config.max_steps is not None and (
        not isinstance(config.max_steps, int) or not 1 <= config.max_steps <= 1_000_000
    ):
        raise EncoderClassifierError("invalid max steps")
    if not isinstance(config.max_length, int) or not 1 <= config.max_length <= 8192:
        raise EncoderClassifierError("invalid sequence length bound")
    if not isinstance(config.learning_rate, (int, float)) or not math.isfinite(config.learning_rate):
        raise EncoderClassifierError("invalid learning rate")
    if config.learning_rate <= 0:
        raise EncoderClassifierError("invalid learning rate")
    if not isinstance(config.head_learning_rate, (int, float)) or not math.isfinite(config.head_learning_rate):
        raise EncoderClassifierError("invalid head learning rate")
    if config.head_learning_rate <= 0:
        raise EncoderClassifierError("invalid head learning rate")
    if not isinstance(config.progress_every, int) or config.progress_every < 0:
        raise EncoderClassifierError("invalid progress interval")


def _layers(module: Any) -> list[Any]:
    for path in (
        ("encoder", "layer"),
        ("encoder", "layers"),
        ("model", "layers"),
        ("layers",),
        ("backbone", "encoder", "layer"),
    ):
        obj = module
        for name in path:
            obj = getattr(obj, name, None)
            if obj is None:
                break
        if obj is not None and not isinstance(obj, type(module)):
            try:
                return list(obj)
            except TypeError:
                pass
    return []


def configure_encoder_training(encoder: Any, last_n_layers: int) -> None:
    if not isinstance(last_n_layers, int) or last_n_layers < -1:
        raise EncoderClassifierError("invalid fine-tune layer count")
    for param in encoder.parameters():
        param.requires_grad_(last_n_layers == -1)
    if last_n_layers in (-1, 0):
        return
    layers = _layers(encoder)
    if not layers:
        raise EncoderClassifierError("encoder layers unavailable for last-N tuning")
    for layer in layers[-last_n_layers:]:
        for param in layer.parameters():
            param.requires_grad_(True)


class EncoderClassifierModel(_torch().nn.Module):
    def __init__(self, encoder: Any, families: list[str], *, max_length: int) -> None:
        torch = _torch()
        super().__init__()
        hidden = int(getattr(getattr(encoder, "config", None), "hidden_size", 0))
        if hidden <= 0:
            raise EncoderClassifierError("encoder hidden size unavailable")
        if not families or any(not isinstance(f, str) or not f for f in families):
            raise EncoderClassifierError("invalid task families")
        self.encoder = encoder
        self.hidden_size = hidden
        self.max_length = max_length
        self.families = sorted(set(families))
        self.heads = torch.nn.ModuleDict({
            f: torch.nn.Sequential(
                torch.nn.Linear(hidden * 4, hidden),
                torch.nn.GELU(),
                torch.nn.Linear(hidden, 1),
            )
            for f in self.families
        })
        self.abstain_heads = torch.nn.ModuleDict({
            f: torch.nn.Sequential(
                torch.nn.Linear(hidden, max(1, hidden // 2)),
                torch.nn.GELU(),
                torch.nn.Linear(max(1, hidden // 2), 1),
            )
            for f in self.families
        })

    def encode_texts(self, tokenizer: Any, texts: list[str], *, device: str | None = None):
        torch = _torch()
        if not texts or any(not isinstance(text, str) or not text for text in texts):
            raise EncoderClassifierError("invalid encoder texts")
        batch = tokenizer(texts, padding=True, truncation=False, return_tensors="pt")
        input_ids = batch["input_ids"]
        if int(input_ids.shape[1]) > self.max_length:
            raise EncoderClassifierError("sequence length exceeds configured bound")
        target = device or next(self.parameters()).device
        if hasattr(batch, "to"):
            batch = batch.to(target)
        else:
            batch = {key: value.to(target) for key, value in batch.items()}
        output = self.encoder(**batch)
        states = output.last_hidden_state
        mask = batch.get("attention_mask")
        if mask is None:
            return states[:, 0, :]
        weights = mask.to(dtype=states.dtype).unsqueeze(-1)
        denom = weights.sum(dim=1).clamp_min(torch.tensor(1, device=states.device))
        return (states * weights).sum(dim=1) / denom

    def score_embeddings(self, task_family: str, query, candidates):
        torch = _torch()
        if task_family not in self.heads:
            raise EncoderClassifierError("unknown task family")
        q = query.expand(candidates.shape[0], -1)
        pair = torch.cat([q, candidates, q * candidates, torch.abs(q - candidates)], dim=1)
        return self.heads[task_family](pair).squeeze(-1)

    def abstain_logit(self, task_family: str, query):
        if task_family not in self.abstain_heads:
            raise EncoderClassifierError("unknown task family")
        return self.abstain_heads[task_family](query).reshape(())


def _row_loss(model: EncoderClassifierModel, tokenizer: Any, row: dict, device: str):
    torch = _torch()
    request = row["request"]
    choices = list(request["choices"])
    texts = [request["state"]] + [choice["description"] for choice in choices]
    reps = model.encode_texts(tokenizer, texts, device=device)
    query, candidate_reps = reps[0], reps[1:]
    choice_ids = [choice["id"] for choice in choices]
    eligible = [cid for cid in request["eligible_choice_ids"] if cid in choice_ids]
    eligible_indexes = [choice_ids.index(cid) for cid in eligible]
    if eligible_indexes:
        logits = model.score_embeddings(row["task_family"], query, candidate_reps[eligible_indexes])
    else:
        logits = torch.empty(0, device=query.device)
    abstain = model.abstain_logit(row["task_family"], query).reshape(1)
    all_logits = torch.cat([logits, abstain])
    acceptable = set(row["acceptable_choice_ids"])
    if acceptable:
        target_indexes = [i for i, cid in enumerate(eligible) if cid in acceptable]
        target = logits[target_indexes]
    else:
        target = abstain
    return torch.logsumexp(all_logits, dim=0) - torch.logsumexp(target, dim=0)


def train_encoder_classifier(
    examples: list[dict],
    *,
    tokenizer: Any,
    encoder: Any,
    config: EncoderTrainConfig | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> EncoderTrainingResult:
    torch = _torch()
    cfg = config or EncoderTrainConfig()
    _check_config(cfg)
    if not isinstance(examples, list) or not examples or len(examples) > 100_000:
        raise EncoderClassifierError("examples must be a bounded non-empty list")
    random.seed(cfg.seed)
    torch.manual_seed(cfg.seed)
    rows = [validate_example(item) for item in examples]
    families = sorted({row["task_family"] for row in rows})
    configure_encoder_training(encoder, cfg.fine_tune_last_n_layers)
    model = EncoderClassifierModel(encoder, families, max_length=cfg.max_length).to(cfg.device)
    head_ids = {id(param) for param in model.heads.parameters()}
    head_ids.update(id(param) for param in model.abstain_heads.parameters())
    head_params = [param for param in model.parameters() if id(param) in head_ids and param.requires_grad]
    encoder_params = [param for param in model.parameters() if id(param) not in head_ids and param.requires_grad]
    if not head_params and not encoder_params:
        raise EncoderClassifierError("no trainable classifier parameters")
    groups = []
    if encoder_params:
        groups.append({"params": encoder_params, "lr": float(cfg.learning_rate)})
    if head_params:
        groups.append({"params": head_params, "lr": float(cfg.head_learning_rate)})
    opt = torch.optim.AdamW(groups)
    losses: list[float] = []
    steps = examples_processed = 0
    pending = []
    rng = random.Random(cfg.seed)
    for _epoch in range(cfg.epochs):
        epoch_rows = list(rows)
        rng.shuffle(epoch_rows)
        for row in epoch_rows:
            pending.append(_row_loss(model, tokenizer, row, cfg.device))
            examples_processed += 1
            if len(pending) < cfg.batch_size:
                continue
            loss = torch.stack(pending).mean()
            loss.backward()
            opt.step()
            opt.zero_grad(set_to_none=True)
            losses.append(float(loss.detach().cpu()))
            pending.clear()
            steps += 1
            if progress_callback and cfg.progress_every and steps % cfg.progress_every == 0:
                progress_callback({"step": steps, "loss": losses[-1],
                                   "examples_processed": examples_processed})
            if cfg.max_steps is not None and steps >= cfg.max_steps:
                break
        if cfg.max_steps is not None and steps >= cfg.max_steps:
            break
    if pending and (cfg.max_steps is None or steps < cfg.max_steps):
        loss = torch.stack(pending).mean()
        loss.backward()
        opt.step()
        opt.zero_grad(set_to_none=True)
        losses.append(float(loss.detach().cpu()))
        steps += 1
        if progress_callback and cfg.progress_every and steps % cfg.progress_every == 0:
            progress_callback({"step": steps, "loss": losses[-1],
                               "examples_processed": examples_processed})
    report = build_training_report(
        rows=rows, config=cfg, families=families, steps=steps,
        examples_processed=examples_processed, losses=losses, model=model)
    return EncoderTrainingResult(model=model, tokenizer=tokenizer, report=report)


def load_local_pretrained(model_dir: str, *, device: str = "cpu", attn_implementation: str = "sdpa"):
    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        raise EncoderClassifierError("transformers is required for pretrained encoder loading") from exc
    tokenizer = AutoTokenizer.from_pretrained(
        model_dir, local_files_only=True, trust_remote_code=False)
    encoder = AutoModel.from_pretrained(
        model_dir,
        local_files_only=True,
        trust_remote_code=False,
        use_safetensors=True,
        attn_implementation=attn_implementation,
    ).to(device)
    return tokenizer, encoder
