#!/usr/bin/env python3
"""
qlora_cpt.py — Phase 2: QLoRA continued-pretraining on the packed corpus.

Loads the base model in 4-bit (nf4 + double-quant, bf16 compute), attaches LoRA
adapters, and trains next-token prediction over the pre-packed uint32 shards
produced by dataset/tokenize_pack.py. Designed for a single 24 GB RTX 4090:
gradient checkpointing on, paged 8-bit optimizer, per-device batch 1 with
accumulation. Resumable via HF Trainer checkpoints on E:.

--smoke runs a 2-step fit on a tiny slice to prove the VRAM envelope BEFORE the
full multi-hour run. Always smoke first on a fresh box.

PRIVACY: trains on opaque token ids only; no source path is read here.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset


# ---------------------------------------------------------------- dataset ----
class PackedShards(Dataset):
    """Memory-mapped view over shard_*.npy as fixed-length training sequences."""

    def __init__(self, packed_dir: str, seq_len: int):
        self.seq_len = seq_len
        self.shards = sorted(Path(packed_dir).glob("shard_*.npy"))
        if not self.shards:
            raise FileNotFoundError(f"no shard_*.npy in {packed_dir}")
        self._mm: list[np.memmap | None] = [None] * len(self.shards)
        self._index: list[tuple[int, int]] = []  # (shard_i, seq_within_shard)
        for si, sp in enumerate(self.shards):
            n_tok = np.load(sp, mmap_mode="r").shape[0]
            for k in range(n_tok // seq_len):
                self._index.append((si, k))

    def __len__(self) -> int:
        return len(self._index)

    def _shard(self, si: int) -> np.memmap:
        mm = self._mm[si]
        if mm is None:
            mm = np.load(self.shards[si], mmap_mode="r")
            self._mm[si] = mm
        return mm

    def __getitem__(self, idx: int) -> dict:
        si, k = self._index[idx]
        mm = self._shard(si)
        lo = k * self.seq_len
        block = np.asarray(mm[lo:lo + self.seq_len], dtype=np.int64)
        ids = torch.from_numpy(block)
        return {"input_ids": ids, "labels": ids.clone()}


def collate(batch: list[dict]) -> dict:
    return {
        "input_ids": torch.stack([b["input_ids"] for b in batch]),
        "labels": torch.stack([b["labels"] for b in batch]),
    }


# ------------------------------------------------------------------ model ----
_LORA_TARGET_PRESETS = {
    "all": ["q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj"],
    "attn": ["q_proj", "k_proj", "v_proj", "o_proj"],
}


def build_model(model_path: str, lora_r: int = 16, lora_targets: str = "all",
                attn_impl: str = "sdpa"):
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    target_modules = _LORA_TARGET_PRESETS.get(lora_targets)
    if target_modules is None:
        raise SystemExit(f"[qlora_cpt] unknown --lora-targets {lora_targets!r}; "
                         f"choose one of {sorted(_LORA_TARGET_PRESETS)}")

    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb,
        device_map={"": 0},
        torch_dtype=torch.bfloat16,
        attn_implementation=attn_impl,
    )
    model.config.use_cache = False
    # NOTE: do NOT enable grad checkpointing here. TrainingArguments owns it
    # (gradient_checkpointing=True + use_reentrant=False below). Enabling in both
    # places causes a reentrant/non-reentrant mismatch that deadlocks the backward
    # pass on Windows + bitsandbytes (hang at step 0). Dedup: enable once, in args.
    #
    # Manual kbit prep WITHOUT the blanket fp32 upcast. prepare_model_for_kbit_training
    # upcasts every bf16 non-Params4bit param (lm_head/embed_tokens) to fp32, which adds
    # ~3GB on the 32B and OOMs a 24GB card at model-prep time (before training). Compute
    # is bf16 anyway, so keeping lm_head bf16 is numerically fine. We do the two parts
    # that matter: freeze the base + enable input grads (for checkpointing grad flow).
    for param in model.parameters():
        param.requires_grad_(False)
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    lora = LoraConfig(
        r=lora_r, lora_alpha=2 * lora_r, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=target_modules,
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    return model


def latest_checkpoint(output_dir: Path) -> Path | None:
    if not output_dir.exists():
        return None

    candidates: list[tuple[int, Path]] = []
    for candidate in output_dir.glob("checkpoint-*"):
        if not candidate.is_dir():
            continue
        step = candidate.name.removeprefix("checkpoint-")
        if step.isdigit():
            candidates.append((int(step), candidate))

    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p[0])[-1][1]


def checkpoint_step(ckpt: Path) -> int:
    return int(ckpt.name.removeprefix("checkpoint-"))


def ensure_trainer_state(ckpt: Path) -> Path:
    trainer_state = ckpt / "trainer_state.json"
    if trainer_state.exists():
        return trainer_state

    step = checkpoint_step(ckpt)
    state = {
        "best_global_step": None,
        "best_metric": None,
        "best_model_checkpoint": str(ckpt),
        "epoch": 0,
        "eval_steps": 500,
        "global_step": step,
        "is_hyper_param_search": False,
        "is_local_process_zero": True,
        "is_world_process_zero": True,
        "log_history": [],
        "logging_steps": 500,
        "max_steps": 0,
        "num_input_tokens_seen": 0,
        "num_train_epochs": 0,
        "save_steps": 50,
        "stateful_callbacks": {},
        "total_flos": 0.0,
        "train_batch_size": None,
        "trial_name": None,
        "trial_params": None,
    }
    with trainer_state.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    print(f"[qlora_cpt] created fallback trainer state at {trainer_state}")
    return trainer_state


def build_args(a):
    from transformers import TrainingArguments
    return TrainingArguments(
        output_dir=a.out,
        per_device_train_batch_size=a.batch,
        gradient_accumulation_steps=a.accum,
        num_train_epochs=a.epochs,
        learning_rate=a.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        weight_decay=0.0,
        bf16=True,
        gradient_checkpointing=a.grad_ckpt,
        gradient_checkpointing_kwargs={"use_reentrant": a.use_reentrant},
        optim="paged_adamw_8bit",
        logging_steps=10,
        save_steps=a.save_steps,
        save_total_limit=3,
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        remove_unused_columns=False,
        report_to="none",
        logging_dir=str(Path(a.out) / "trainer-logs"),
        **({"deepspeed": a.deepspeed} if a.deepspeed else {}),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model",
                    default=r"E:\local-model-run\models\Qwen2.5-Coder-32B-Instruct")
    ap.add_argument("--packed", default=r"E:\local-model-run\data\packed")
    ap.add_argument("--out",
                    default=r"E:\local-model-run\checkpoints\phase2-qlora-cpt-32b")
    ap.add_argument("--seq-len", type=int, default=2048)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-targets", choices=["all", "attn"], default="all",
                    help="LoRA target preset: all (7 modules, default) or attn "
                         "(q,k,v,o only -- smaller kernels for VRAM/TDR smokes)")
    ap.add_argument("--attn", choices=["sdpa", "eager", "flash_attention_2"],
                    default="sdpa",
                    help="attention impl; try 'eager' if sdpa deadlocks with "
                         "grad-checkpointing + 4-bit (hang at step 0)")
    ap.add_argument("--no-grad-ckpt", dest="grad_ckpt", action="store_false",
                    help="disable gradient checkpointing (needs small seq_len "
                         "to fit VRAM; isolates grad-ckpt as the hang cause)")
    ap.set_defaults(grad_ckpt=True)
    ap.add_argument("--use-reentrant", dest="use_reentrant", action="store_true",
                    help="use reentrant grad checkpointing (default non-reentrant; "
                         "reentrant sometimes works where non-reentrant deadlocks)")
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--accum", type=int, default=32)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--lr", type=float, default=1.5e-4)
    ap.add_argument("--save-steps", type=int, default=50)
    ap.add_argument("--deepspeed", default=None,
                    help="path to a DeepSpeed config json; enables the memory-"
                         "layer activation-offload path for models that OOM in "
                         "backward (e.g. 32B at seq_len 2048 on 24GB)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--smoke", action="store_true",
                    help="2-step fit on a tiny slice to prove the VRAM envelope")
    a = ap.parse_args()

    from transformers import Trainer

    ds = PackedShards(a.packed, a.seq_len)
    print(f"[qlora_cpt] dataset: {len(ds)} sequences of {a.seq_len} tokens "
          f"(~{len(ds) * a.seq_len / 1e6:.1f}M tokens)")

    if a.smoke:
        a.out = a.out + "-smoke"
        a.epochs = 1.0
        a.save_steps = 100000
        ds = torch.utils.data.Subset(ds, list(range(min(4 * a.accum, len(ds)))))

    model = build_model(a.model, a.lora_r, a.lora_targets, a.attn)
    args = build_args(a)
    trainer = Trainer(model=model, args=args, train_dataset=ds,
                      data_collator=collate)

    if a.smoke:
        trainer.args.max_steps = 2
        trainer.train()
        ckpt = latest_checkpoint(Path(a.out))
        if ckpt is None and trainer.state.global_step > 0:
            ckpt = Path(a.out) / f"checkpoint-{trainer.state.global_step}"
        if ckpt is None:
            raise RuntimeError(f"[qlora_cpt] smoke finished but no checkpoint was found in {a.out}")
        ckpt.mkdir(parents=True, exist_ok=True)
        # transformers 5.x TrainerState has no to_dict(); reuse the stub writer
        # (the smoke is a 2-step envelope test, not a resumable training trace).
        ensure_trainer_state(ckpt)
        print(f"[qlora_cpt] smoke checkpoint at {ckpt}")
        free, total = torch.cuda.mem_get_info()
        peak = torch.cuda.max_memory_allocated() / 1e9
        print(json.dumps({
            "smoke": "ok", "peak_alloc_GB": round(peak, 2),
            "free_GB": round(free / 1e9, 2), "total_GB": round(total / 1e9, 2),
        }, indent=2))
        return 0

    resume_checkpoint = None
    if a.resume:
        resume_checkpoint = latest_checkpoint(Path(a.out))
        if resume_checkpoint is None:
            resume_checkpoint = latest_checkpoint(Path(a.out + "-smoke"))
            if resume_checkpoint is not None:
                print(f"[qlora_cpt] --resume target resolved to smoke checkpoint: {resume_checkpoint}")
    if resume_checkpoint is not None:
        ensure_trainer_state(resume_checkpoint)
    if resume_checkpoint is not None:
        trainer.train(resume_from_checkpoint=str(resume_checkpoint))
    else:
        if a.resume:
            print("[qlora_cpt] --resume requested but no checkpoint exists; starting from scratch")
        trainer.train()
    trainer.save_model(a.out)
    print(f"[qlora_cpt] DONE — adapter saved to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
