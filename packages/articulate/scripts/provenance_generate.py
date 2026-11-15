"""Generate the AI and mixed documents of the known-provenance corpus locally.

    node <gpu-lock.mjs> run provenance-gen -- python scripts/provenance_generate.py --model qwen2.5:7b

Every call goes to the local Ollama server on 127.0.0.1. Each document records
the model name and digest, the Ollama version, the exact prompt (or, for a
prompt drawn from a corpus that stays local, its hash), the seed, the sampling
options and the date. A document already in the manifest is skipped, so an
interrupted run resumes where it stopped.
"""
import argparse
import datetime
import json
import urllib.request

import provenance_common as C

OLLAMA = "http://127.0.0.1:11434"
OPTIONS = {"temperature": 0.8, "top_p": 0.95, "num_predict": 900}
LITERARY = {
    "fiction": ("Write a passage of about 350 words from a novel. {topic}. "
                "Write only the passage, with no title or preface.",
                ["A sailor on a whaling ship describes a calm morning at sea",
                 "A narrator explains how a world with only two dimensions looks to the people in it",
                 "Three friends on a boating holiday on the Thames argue about what to pack"]),
    "essay": ("Write a reflective essay of about 350 words about {topic}. "
              "Write only the essay, with no title.",
              ["living simply in a cabin beside a pond", "why people fill their days with errands",
               "the value of solitude"]),
    "science": ("Write about 350 words of natural-history writing for general readers about "
                "{topic}. Write only the text, with no title.",
                ["how variation within a species is passed from parents to offspring",
                 "the geology and wildlife of a remote volcanic island chain",
                 "how earthworms change the soil of a field over many years"]),
}
ESSAY_TEMPLATE = "{assignment}\n\nWrite the essay. Write only the essay, with no title."
EDIT_INSTRUCTION = ("Edit the following text for clarity and flow. Keep its meaning, its point "
                    "of view and roughly its length. Return only the edited text.\n\n")
EDITORS = {"qwen2.5:7b", "olmo2:7b"}
ESSAY_SEEDS = (1, 2)


def _post(path, body, timeout=600):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path):
    with urllib.request.urlopen(OLLAMA + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def model_info(model):
    tags = {m["name"]: m for m in _get("/api/tags")["models"]}
    m = tags[model]
    return {"model": model, "digest": m["digest"], "family": m["details"].get("family"),
            "parameter_size": m["details"].get("parameter_size"),
            "quantization": m["details"].get("quantization_level"),
            "ollama_version": _get("/api/version")["version"], "server": "local Ollama"}


def generate(model, prompt, seed):
    body = {"model": model, "prompt": prompt, "stream": False, "keep_alive": "2m",
            "options": dict(OPTIONS, seed=seed)}
    if model.startswith("qwen3"):
        body["think"] = False
    r = _post("/api/generate", body)
    text = r["response"].split("</think>")[-1].strip() + "\n"
    return text, {"done_reason": r.get("done_reason"), "eval_count": r.get("eval_count")}


def _record(man, doc, text, local_root):
    if C.upsert(man, doc):
        C.write_text(doc, text, local_root)
        C.save_manifest(man)
        print(f"{doc['id']}: {doc['words']} words ({doc['generation']['result']['done_reason']})")


def _gen_doc(doc_id, genre, location, info, prompt_rec, seed, text, result, when):
    sub = "ai" if doc_id.startswith("ai-") else "mixed"
    return {"id": doc_id, "class": sub, "genre": genre, "location": location,
            "path": f"{sub}/{doc_id}.txt", "sha256": C.sha256_text(text), "words": C.words(text),
            "written": when,
            "generation": dict(info, seed=seed, options=OPTIONS, date=when, result=result, **prompt_rec)}


def literary(man, model, info, when, local_root):
    tag = model.replace(":", "-")
    for genre, (template, topics) in LITERARY.items():
        for i, topic in enumerate(topics):
            doc_id = f"ai-{genre}-{i}-{tag}"
            if any(d["id"] == doc_id for d in man["documents"]):
                continue
            prompt = template.format(topic=topic)
            text, result = generate(model, prompt, seed=i + 1)
            doc = _gen_doc(doc_id, genre, "repo", info, {"prompt": prompt}, i + 1, text, result, when)
            _record(man, doc, text, local_root)


def student(man, model, info, when, local_root, assignments):
    tag = model.replace(":", "-")
    for name, assignment in sorted(assignments.items()):
        for seed in ESSAY_SEEDS:
            slug = name.lower().replace(" ", "-")
            doc_id = f"ai-student-essay-{slug}-{seed}-{tag}"
            if any(d["id"] == doc_id for d in man["documents"]):
                continue
            prompt = ESSAY_TEMPLATE.format(assignment=assignment)
            text, result = generate(model, prompt, seed)
            rec = {"prompt_template": ESSAY_TEMPLATE, "prompt_name": name,
                   "prompt_sha256": C.sha256_text(prompt),
                   "prompt_note": "assignment text from PERSUADE 2.0; kept local"}
            doc = _gen_doc(doc_id, "student-essay", "local", info, rec, seed, text, result, when)
            _record(man, doc, text, local_root)


def edits(man, model, info, when, local_root):
    """AI edits of human documents: one Gutenberg excerpt per book, one essay per prompt."""
    tag = model.replace(":", "-")
    bases = [d for d in list(man["documents"]) if d["class"] == "human" and (
        (d["id"].startswith("human-gutenberg-") and d["id"].endswith("-0")) or _first_essay(man, d))]
    for base in bases:
        doc_id = f"mixed-edit-{base['id'][len('human-'):]}-{tag}"
        if any(d["id"] == doc_id for d in man["documents"]):
            continue
        original = C.read_checked(base, local_root)
        if original is None:
            print(f"skip {base['id']}: text missing or changed")
            continue
        text, result = generate(model, EDIT_INSTRUCTION + original, seed=1)
        rec = {"prompt_template": EDIT_INSTRUCTION + "{text}",
               "edit": {"operation": "AI edit of a human text", "base_id": base["id"],
                        "base_sha256": base["sha256"], "by": model,
                        "instruction": EDIT_INSTRUCTION.strip()}}
        doc = _gen_doc(doc_id, base["genre"], base["location"], info, rec, 1, text, result, when)
        _record(man, doc, text, local_root)


def _first_essay(man, d):
    if not d["id"].startswith("human-persuade-") or d["group"]["ell_status"] != "No":
        return False
    same = sorted(x["id"] for x in man["documents"] if x["id"].startswith("human-persuade-")
                  and x["group"]["prompt_name"] == d["group"]["prompt_name"]
                  and x["group"]["ell_status"] == "No")
    return same[0] == d["id"]


def assignments_from(csv_path, names):
    import csv
    csv.field_size_limit(10 ** 9)
    out = {}
    with open(csv_path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["prompt_name"] in names and row["prompt_name"] not in out:
                out[row["prompt_name"]] = row["assignment"].strip()
            if len(out) == len(names):
                break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--persuade", type=C.pathlib.Path, help="PERSUADE 2.0 CSV, for the essay prompts")
    ap.add_argument("--local-root", type=C.pathlib.Path, default=C.DEFAULT_LOCAL)
    a = ap.parse_args(argv)
    man = C.load_manifest()
    info = model_info(a.model)
    when = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    try:
        literary(man, a.model, info, when, a.local_root)
        if a.persuade:
            from provenance_human import PROMPTS
            student(man, a.model, info, when, a.local_root, assignments_from(a.persuade, set(PROMPTS)))
        if a.model in EDITORS:
            edits(man, a.model, info, when, a.local_root)
    finally:
        _post("/api/generate", {"model": a.model, "keep_alive": 0})  # free the GPU at once


if __name__ == "__main__":
    main()
