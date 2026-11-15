"""The labelled synthetic corpus for the campaign-signal bench.

Two sources, both synthetic, every name and product invented:
  - corpus/campaign/hand.json: hand-written items, organic and templated, with a
    stratum per item (standard, esl, dialect, translated, code_switched,
    non_english, crypto_real, enthusiasm, technical, founder, disclosed);
  - generated() below: slot-filled stock-persona bios and a batch of coordinated
    quote posts and replies with a campaign id per post.
The generator is deterministic. Items alternate between the dev and heldout
splits so each split sees every frame.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2] / "corpus" / "campaign"

ROLES = ["Recruiter", "Plumber", "Dentist", "Chef", "Pilot", "Florist", "Tailor", "Librarian",
         "Mechanic", "Banker"]
PLACES = ["Gambia", "Ohio", "Lima", "Oslo", "Kerala", "Lagos", "Perth", "Quebec", "Cebu", "Krakow"]
HOBBIES = ["Candle Making", "Minimalism", "Origami", "Kayaking", "Baking", "Chess", "Knitting",
           "Surfing", "Running", "Stargazing"]
TOKENS = ["WBTC", "EOS", "SOL", "ETH", "DOGE", "ADA", "XRP", "LINK", "DOT", "AVAX"]
TAGS = ["Here for the memes.", "Cat person.", "Dog lover.", "Traveler.", "Here for the vibes.",
        "Proud dog mom.", "Cat lover.", "Here for the gains."]
FRAMES = [
    "A {role} in {place}, stacking {tok} like a pro. {tag}",
    "Age {age}, still young at heart, passionate about {hobby}. Crypto is the future. | {tagc}",
    "{age} year old dreamer, enjoying life with {hobby} | {tagc}",
    "Obsessed with {tok}, chasing dreams and ${tok}. {tag}",
    "An {role} from {place}, passionate about {hobby}. Stacking {tok} like a boss. {tag}",
]

CAMPAIGNS = {
    "A": ["{op}... they just dropped a coding model that runs LOCALLY on {dev} at {n} tokens/sec",
          ["sir", "bro", "guys", "ser"], ["a MacBook Pro", "a laptop", "an old MacBook", "a mini PC"],
          ["125", "118", "130", "125"]],
    "B": ["Northlake launches Ember, its first model: a fast local coding model built with "
          "{our} automated research system. {tail}",
          ["our", "their", "an", "its"], ["Huge.", "Best-in-class.", "Wild.", "This is big."], []],
    "C": ["This is huge for {who}. Ember is going to change {what}. You need to try it.",
          ["devs", "builders", "founders", "students"], ["coding", "everything", "how we ship",
                                                          "local AI"], []],
}

ORGANIC_REPLIES = [
    "Does it handle Python type hints well? Our codebase is full of them.",
    "Tried it this morning. Fast, but it hallucinated an import twice.",
    "What quantization are they using for the laptop numbers?",
    "125 tokens/sec seems high for a laptop. What context length?",
    "Is there a license file yet? Can't use it at work without one.",
    "Ran it on my desktop with a 3060, about 40 tok/s for me.",
    "Curious how Ember compares to the 7B we already use for autocomplete.",
    "The demo video is nice but I want to see a failure case.",
    "Anyone got it working on Linux? The installer is Mac only.",
    "My kid used it for homework and it explained recursion better than I did.",
    "Not convinced. Local models still struggle with multi-file edits.",
    "Waiting for independent benchmarks before I switch.",
    "Northlake's last product was decent, so I'll give this one a go.",
    "It refused to write a regex for me, weirdly.",
    "Does it run offline after the first download?",
    "Took 20 minutes to download on hotel wifi, works fine now.",
    "Introducing Ember, huh. Who is behind Northlake anyway?",
    "Sir is there a Windows version also?",
    "La versión local funciona bien en mi portátil, gracias.",
    "ノートPCで試しました。速いですが、たまに間違えます。",
]


def _bios():
    out = []
    for i in range(40):
        f = FRAMES[i % len(FRAMES)]
        tag = TAGS[i % len(TAGS)]
        j = i // len(FRAMES)
        text = f.format(role=ROLES[(i + j) % 10], place=PLACES[(j * 3 + i) % 10],
                        hobby=HOBBIES[(j * 7 + i) % 10], tok=TOKENS[(j * 3 + i + 1) % 10],
                        age=23 + (i * 7) % 40, tag=tag,
                        tagc=tag.rstrip("."))
        out.append({"id": f"gb{i:02d}", "kind": "bio", "platform": "x", "stratum": "generated",
                    "label": 1, "split": "dev" if i % 2 == 0 else "heldout", "text": text})
    return out


def batch():
    """Coordinated quote posts (campaign A, B, C) mixed with organic replies (campaign None)."""
    items = []
    for cid, (tmpl, a, b, c) in CAMPAIGNS.items():
        for i in range(8):
            text = tmpl.format(op=a[i % 4], dev=b[i % 4], n=(c or ["0"])[i % len(c or [0])],
                               our=a[i % 4], tail=b[(i + 1) % 4], who=a[i % 4], what=b[(i + 2) % 4])
            items.append({"id": f"{cid}{i}", "kind": "post", "campaign": cid, "text": text})
    for i, t in enumerate(ORGANIC_REPLIES):
        items.append({"id": f"r{i:02d}", "kind": "post", "campaign": None, "text": t})
    return items


def _hand():
    data = json.loads((ROOT / "hand.json").read_text(encoding="utf-8"))
    out = []
    for g in data["groups"]:
        for n, t in enumerate(g["texts"]):
            out.append({"id": f"{g['split'][0]}-{g['kind']}-{g['platform']}-{g['stratum']}-"
                              f"{g['label']}-{n}",
                        "kind": g["kind"], "platform": g["platform"], "stratum": g["stratum"],
                        "label": g["label"], "split": g["split"], "text": t})
    return out


def items(split=None):
    """All labelled per-item rows, optionally one split."""
    rows = _hand() + _bios()
    return [r for r in rows if split is None or r["split"] == split]
