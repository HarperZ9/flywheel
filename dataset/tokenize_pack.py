#!/usr/bin/env python3
"""
tokenize_pack.py — Phase 1: turn the corpus manifest into packed token shards.

Reads manifest.jsonl, tokenizes each file with the base tokenizer, separates
documents with the pretraining EOS token, and packs the concatenated stream
into fixed-length uint32 shards on E:. Deterministic (manifest processed in a
stable sorted order) and resumable (a completed run writes PACK_COMPLETE.json;
partial shards are cleared and re-packed).

PRIVACY: no source path is ever printed or written into an artifact — only
aggregate counts. The packed shards are opaque token ids.

Usage (run with the E: venv python, after the base model is downloaded):
  E:\\local-model-run\\venv\\Scripts\\python.exe dataset/tokenize_pack.py
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np


def log(msg: str) -> None:
    print(f"[tokenize_pack] {msg}", flush=True)


def load_manifest(p: Path) -> list[dict]:
    recs: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            recs.append(json.loads(line))
    # stable, content-independent order → deterministic packing
    recs.sort(key=lambda r: r["path"])
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest",
                    default="C:/dev/local-model/dataset/manifest.jsonl")
    ap.add_argument("--base", default="C:/dev")
    ap.add_argument("--model",
                    default=r"E:\local-model-run\models\Qwen2.5-Coder-14B-Instruct")
    ap.add_argument("--out", default=r"E:\local-model-run\data\packed")
    ap.add_argument("--seq-len", type=int, default=4096)
    ap.add_argument("--shard-seqs", type=int, default=2048,
                    help="sequences per full shard (shard = seq_len*shard_seqs tokens)")
    ap.add_argument("--limit", type=int, default=0,
                    help="debug: cap number of files (0 = all)")
    args = ap.parse_args()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(
        args.model, use_fast=True, trust_remote_code=False)

    sep = tok.convert_tokens_to_ids("<|endoftext|>")
    if sep is None or sep < 0:
        sep = tok.eos_token_id
    vocab = len(tok)
    assert vocab < 2**32, "vocab exceeds uint32 range"
    log(f"tokenizer vocab={vocab} sep_id={sep} seq_len={args.seq_len} "
        f"shard={args.seq_len * args.shard_seqs} tok")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = Path(args.base)

    marker = out / "PACK_COMPLETE.json"
    if marker.exists():
        log("PACK_COMPLETE.json present — corpus already packed. Nothing to do.")
        print(marker.read_text())
        return 0
    # clear any partial shards from an interrupted run
    partials = sorted(out.glob("shard_*.npy"))
    for f in partials:
        f.unlink()
    if partials:
        log(f"cleared {len(partials)} partial shards; re-packing from scratch")

    recs = load_manifest(Path(args.manifest))
    if args.limit:
        recs = recs[:args.limit]
    log(f"{len(recs)} files to pack")

    shard_tokens = args.seq_len * args.shard_seqs
    buf: list[int] = []
    shard_idx = 0
    total_tokens = 0
    files_packed = 0
    skipped = 0
    t0 = time.time()

    def emit_shard(tokens: list[int]) -> None:
        nonlocal shard_idx, total_tokens
        arr = np.asarray(tokens, dtype=np.uint32)
        np.save(out / f"shard_{shard_idx:05d}.npy", arr)
        shard_idx += 1
        total_tokens += int(arr.shape[0])

    for i, r in enumerate(recs):
        fp = base / r["path"]
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):
            skipped += 1
            continue
        ids = tok.encode(text, add_special_tokens=False)
        ids.append(sep)
        buf.extend(ids)
        files_packed += 1

        while len(buf) >= shard_tokens:
            emit_shard(buf[:shard_tokens])
            del buf[:shard_tokens]

        if (i + 1) % 1000 == 0:
            live = total_tokens + len(buf)
            log(f"{i + 1}/{len(recs)} files · {shard_idx} shards · "
                f"{live / 1e6:.1f}M tok · {time.time() - t0:.0f}s")

    # final shard: keep only a whole multiple of seq_len (drop tiny remainder)
    keep = (len(buf) // args.seq_len) * args.seq_len
    dropped_tail = len(buf) - keep
    if keep:
        emit_shard(buf[:keep])

    meta = {
        "seq_len": args.seq_len,
        "dtype": "uint32",
        "sep_id": int(sep),
        "shards": shard_idx,
        "total_tokens": total_tokens,
        "sequences": total_tokens // args.seq_len,
        "files_packed": files_packed,
        "files_skipped": skipped,
        "dropped_tail_tokens": dropped_tail,
        "model": os.path.basename(args.model),
        "shard_glob": "shard_*.npy",
        "layout": "flat uint32 token stream; reshape to (-1, seq_len) at load",
    }
    marker.write_text(json.dumps(meta, indent=2))
    log(f"DONE: {shard_idx} shards · {total_tokens / 1e6:.2f}M tokens · "
        f"{files_packed} files · {skipped} skipped · "
        f"{time.time() - t0:.0f}s")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
