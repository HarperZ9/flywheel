import json, os
from pathlib import Path

private = Path(os.environ["SYFTBOX_FOLDER"]) / "do@example.org" / "private" / "eval"
items = json.loads((private / "items.json").read_text())
model = json.loads((private / "model.json").read_text())


def predict(a, b):
    bump = model["odd_odd_offset"] if a % 2 == 1 and b % 2 == 1 else 0
    return str(a + b + bump)


os.makedirs("outputs", exist_ok=True)
with open("outputs/results.jsonl", "w") as f:
    for it in items:
        p = predict(it["a"], it["b"])
        row = {"item_id": it["id"], "prediction": p, "correct": p.strip() == it["answer"].strip()}
        f.write(json.dumps(row, sort_keys=True) + "\n")
print("rows written:", len(items))
