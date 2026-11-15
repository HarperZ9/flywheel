"""Score the known-provenance corpus with Binoculars and Fast-DetectGPT, locally.

    node <gpu-lock.mjs> run binoculars-observer  -- py -3.13 scripts/provenance_detectors.py observer
    node <gpu-lock.mjs> run binoculars-performer -- py -3.13 scripts/provenance_detectors.py performer

Both detectors are outside comparison points. Nothing in Articulate reads
their scores to set a rule, a gate or an editor setting.

Binoculars (Hans et al. 2024, arXiv 2401.12070): score = log-perplexity of the
text under the performer / cross-perplexity, the observer's next-token
distribution scored by the performer's log-probabilities. Lower reads as more
machine-like. The paper's pair is Falcon-7B (observer) and Falcon-7B-instruct
(performer); this run uses the Qwen3-VL 4B and 8B instruct models already on
disk, which share one tokenizer. The paper's thresholds do not transfer to
another pair, so only threshold-free measures are reported.

Fast-DetectGPT (Bao et al. 2024, arXiv 2310.05130), analytic white-box form
with the observer as both sampling and scoring model: (sum log p(x_t) - sum
E[log p]) / sqrt(sum Var[log p]). Higher reads as more machine-like.

The run needs the full observer distribution at each position while the
performer runs, and the two models do not fit on the GPU together. Pass one
stores the observer's top 2,048 probabilities per position; pass two uses
them, renormalised. Each record carries the probability mass left out.
"""
import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys

import provenance_common as C

HUB = pathlib.Path(os.environ.get("HF_HUB_CACHE", "hf-cache/hub"))
OBSERVER = ("Qwen/Qwen3-VL-4B-Instruct", "ebb281ec70b05090aa6165b016eac8ec08e71b17")
PERFORMER = ("Qwen/Qwen3-VL-8B-Instruct", "0c351dd01ed87e9c1b53cbc748cba10e6187ff3b")
MAX_TOKENS = 512
TOPK = 2048
WORK = pathlib.Path(os.environ.get("ARTICULATE_PROVENANCE_WORK", "provenance-detector-work"))
RECORDS = C.PROV / "detector-records.jsonl"


def snapshot(repo_rev):
    repo, rev = repo_rev
    return HUB / f"models--{repo.replace('/', '--')}" / "snapshots" / rev


def load(repo_rev):
    """Build the model on the GPU, then copy each checkpoint tensor in, one shard at a
    time. from_pretrained crashed while memory-mapping the 8B shards on this machine."""
    import torch
    from safetensors import safe_open
    from transformers import AutoConfig, AutoTokenizer, Qwen3VLForConditionalGeneration
    path = snapshot(repo_rev)
    tok = AutoTokenizer.from_pretrained(path)
    config = AutoConfig.from_pretrained(path)
    with torch.device("cuda"):
        model = Qwen3VLForConditionalGeneration._from_config(config, dtype=torch.bfloat16)
    params = dict(model.named_parameters())
    seen = set()
    for shard in sorted(path.glob("*.safetensors")):
        with safe_open(str(shard), "pt", device="cpu") as fh:
            for key in fh.keys():
                if key not in params:
                    if key != "lm_head.weight":
                        raise ValueError(f"{repo_rev[0]}: checkpoint key {key} has no parameter")
                    continue  # tied to the input embedding
                with torch.no_grad():
                    params[key].copy_(fh.get_tensor(key))
                seen.add(key)
    model.tie_weights()
    missing = set(params) - seen
    if missing:
        raise ValueError(f"{repo_rev[0]}: {len(missing)} parameters not in the checkpoint")
    model.eval()
    return tok, model


def logprobs(tok, model, text):
    """(token ids predicted, log-softmax over the vocabulary at each step), float32."""
    import torch
    ids = tok(text, return_tensors="pt", truncation=True, max_length=MAX_TOKENS).input_ids.to("cuda")
    with torch.no_grad():
        logits = model(input_ids=ids).logits[0, :-1].float()
    return ids[0, 1:], torch.log_softmax(logits, dim=-1)


def documents(local_root):
    for doc in C.load_manifest()["documents"]:
        text = C.read_checked(doc, local_root)
        if text is None:
            print(f"skip {doc['id']}: text missing or changed")
            continue
        yield doc, text


def observer_pass(local_root):
    import torch
    tok, model = load(OBSERVER)
    WORK.mkdir(parents=True, exist_ok=True)
    for doc, text in documents(local_root):
        target, lp = logprobs(tok, model, text)
        p = lp.exp()
        top_p, top_i = p.topk(TOPK, dim=-1)
        lp_x = lp.gather(1, target[:, None])[:, 0]
        mean = (p * lp).sum(-1)
        var = (p * lp * lp).sum(-1) - mean * mean
        fdg = ((lp_x.sum() - mean.sum()) / var.sum().sqrt()).item()
        torch.save({"sha256": doc["sha256"], "target": target.cpu(), "top_p": top_p.half().cpu(),
                    "top_i": top_i.int().cpu(), "fast_detectgpt": fdg,
                    "tokens": int(target.numel())}, WORK / f"{doc['id']}.pt")
    print("observer pass done")


def performer_pass(local_root):
    import torch
    tok, model = load(PERFORMER)
    out = []
    for doc, text in documents(local_root):
        saved = torch.load(WORK / f"{doc['id']}.pt")
        if saved["sha256"] != doc["sha256"]:
            raise ValueError(f"{doc['id']}: observer pass ran on other text")
        target, lp = logprobs(tok, model, text)
        if not torch.equal(target.cpu(), saved["target"]):
            raise ValueError(f"{doc['id']}: the two tokenisations differ")
        top_p = saved["top_p"].float().to("cuda")
        residual = (1 - top_p.sum(-1)).clamp(min=0)
        top_p = top_p / top_p.sum(-1, keepdim=True)
        x_ent = -(top_p * lp.gather(1, saved["top_i"].long().to("cuda"))).sum(-1).mean()
        ppl = -lp.gather(1, target[:, None])[:, 0].mean()
        out.append((doc, saved, (ppl / x_ent).item(), residual.mean().item()))
    write_records(out)


def _versions():
    import torch
    import transformers
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.ROOT, capture_output=True, text=True)
    return {"torch": torch.__version__, "transformers": transformers.__version__,
            "python": sys.version.split()[0], "articulate_commit": head.stdout.strip(),
            "script_sha256": C.sha256_text(pathlib.Path(__file__).read_text(encoding="utf-8"))}


def write_records(rows):
    when = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    env = _versions()
    pair = {"observer": "@".join(OBSERVER), "performer": "@".join(PERFORMER)}
    with open(RECORDS, "a", encoding="utf-8", newline="\n") as fh:
        for doc, saved, bino, residual in rows:
            base = {"schema": 1, "text_id": doc["id"], "text_sha256": doc["sha256"],
                    "tokens": saved["tokens"], "max_tokens": MAX_TOKENS, "observed": when,
                    "environment": env}
            fh.write(json.dumps(dict(base, detector="binoculars", version="hans-2024-reimplemented",
                                     models=pair, topk=TOPK, residual_mass=round(residual, 6),
                                     score=round(bino, 6), direction="lower reads as machine-like"),
                                sort_keys=True) + "\n")
            fh.write(json.dumps(dict(base, detector="fast-detectgpt", version="bao-2024-analytic-white-box",
                                     models={"sampling": pair["observer"], "scoring": pair["observer"]},
                                     score=round(saved["fast_detectgpt"], 6),
                                     direction="higher reads as machine-like"), sort_keys=True) + "\n")
    print(f"{len(rows)} documents scored; records appended to {RECORDS}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("passname", choices=["observer", "performer"])
    ap.add_argument("--local-root", type=pathlib.Path, default=C.DEFAULT_LOCAL)
    a = ap.parse_args(argv)
    (observer_pass if a.passname == "observer" else performer_pass)(a.local_root)


if __name__ == "__main__":
    main()
