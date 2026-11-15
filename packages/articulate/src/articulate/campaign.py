"""Campaign signals over a batch of short texts: the API behind `articulate campaign`.

analyze(items, platform=...) takes a list of strings or objects
{"id", "text", "kind": "post" | "bio", "platform"} and returns one report with
format "articulate-campaign-report/1". The schema is in docs/campaign.md and
docs/campaign-schema.json; it is the stable surface other tools call or mirror.

Three passes:
  1. per item: promotional-template findings (posts) or stock-persona slots (bios);
  2. clusters of near-duplicate or templated posts, each with a shared skeleton;
  3. groups of bios that share a slot frame once the fillers are masked.
Nothing is edited. A report says where to look; a person decides what it means.
"""
from . import campaign_cluster, campaign_persona, campaign_promo

FORMAT = "articulate-campaign-report/1"
KINDS = ("post", "bio")
PLATFORMS = tuple(campaign_persona.PLATFORMS)
SCOPE = (
    "These signals describe the form of the text. They do not show that an account is a bot, "
    "that anyone was paid, or who wrote a post. Similar posts can come from many people "
    "quoting one announcement; template-shaped bios are common among real people. Treat a hit "
    "as a reason to look, and never as a verdict about a person.")


class CampaignInputError(ValueError):
    """The input is not a list of texts or {id, text, kind} objects."""


def _coerce(items, platform):
    if not isinstance(items, list):
        raise CampaignInputError("input must be a JSON list")
    out = []
    for n, it in enumerate(items):
        if isinstance(it, str):
            it = {"text": it}
        if not isinstance(it, dict) or not isinstance(it.get("text"), str):
            raise CampaignInputError(f"item {n} needs a string 'text'")
        kind = it.get("kind", "post")
        if kind not in KINDS:
            raise CampaignInputError(f"item {n}: kind must be one of {', '.join(KINDS)}")
        plat = it.get("platform", platform)
        if plat not in PLATFORMS:
            raise CampaignInputError(f"item {n}: platform must be one of {', '.join(PLATFORMS)}")
        out.append({"id": str(it.get("id", n)), "text": it["text"], "kind": kind,
                    "platform": plat})
    return out


def _item_report(it, promo_threshold):
    if it["kind"] == "bio":
        a = campaign_persona.assess(it["text"], it["platform"])
        return {"id": it["id"], "kind": "bio", "platform": it["platform"],
                "template": a["template"], "score": a["score"], "findings": a["findings"],
                "slots": a["slots"], "slot_types": a["slot_types"], "frame": a["frame"]}
    a = campaign_promo.assess(it["text"], promo_threshold)
    return {"id": it["id"], "kind": "post", "platform": it["platform"],
            "template": a["template"], "score": a["score"], "findings": a["findings"]}


def _clusters(items, idx, threshold, texts=None):
    texts = texts if texts is not None else [items[i]["text"] for i in idx]
    out = []
    for c in campaign_cluster.cluster(texts, threshold=threshold):
        members = [texts[i] for i in c["members"]]
        sk = campaign_cluster.skeleton(members)
        kind = "near_duplicate" if c["similarity_min"] >= 0.9 else "template"
        out.append({"ids": [items[idx[i]]["id"] for i in c["members"]], "size": c["size"],
                    "kind": kind, "similarity_min": c["similarity_min"],
                    "similarity_max": c["similarity_max"], "skeleton": sk["skeleton"],
                    "shared_tokens": sk["shared_tokens"], "fillers": sk["fillers"]})
    return out


def analyze(items, *, platform="generic", cluster_threshold=0.5, frame_threshold=0.6,
            promo_threshold=3):
    """Run the three passes and return one report dict (format FORMAT)."""
    if platform not in PLATFORMS:
        raise CampaignInputError(f"platform must be one of {', '.join(PLATFORMS)}")
    its = _coerce(items, platform)
    reports = [_item_report(it, promo_threshold) for it in its]
    posts = [i for i, it in enumerate(its) if it["kind"] == "post"]
    bios = [i for i, it in enumerate(its) if it["kind"] == "bio"]
    clusters = _clusters(its, posts, cluster_threshold)
    frames = [reports[i]["frame"] for i in bios]
    groups = _clusters(its, bios, frame_threshold, texts=frames)
    clustered = sum(c["size"] for c in clusters)
    return {
        "format": FORMAT, "platform": platform,
        "parameters": {"cluster_threshold": cluster_threshold,
                       "frame_threshold": frame_threshold, "promo_threshold": promo_threshold},
        "items": reports, "clusters": clusters, "persona_groups": groups,
        "summary": {"items": len(its), "posts": len(posts), "bios": len(bios),
                    "promo_templates": sum(1 for r in reports
                                           if r["kind"] == "post" and r["template"]),
                    "persona_templates": sum(1 for r in reports
                                             if r["kind"] == "bio" and r["template"]),
                    "clusters": len(clusters), "posts_in_clusters": clustered,
                    "persona_groups": len(groups)},
        "scope": SCOPE}
