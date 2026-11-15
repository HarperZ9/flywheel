"""`articulate campaign`: promotional-template, persona-bio and clustering signals.

    articulate campaign FILE [--platform x|reddit|tiktok|linkedin|generic]
                        [--json] [--threshold J] [--frame-threshold J]

FILE is a JSON list of strings or {id, text, kind, platform} objects; `-` reads
standard input. Prints a summary, or the full report as JSON (schema in
docs/campaign.md). Exit 0 on success, 2 on unreadable input. Nothing is edited.
"""
import json
import sys

from . import campaign


def _load(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _print_summary(r):
    s = r["summary"]
    print(f"[articulate] campaign [{r['platform']}]: {s['items']} items, "
          f"{s['promo_templates']} promo templates, {s['persona_templates']} stock-persona bios, "
          f"{s['clusters']} clusters ({s['posts_in_clusters']} posts), "
          f"{s['persona_groups']} bio frame groups")
    for it in r["items"]:
        for f in it["findings"]:
            print(f"  {it['id']}:{f['col']}  {f['label']}: {f['match']!r}")
            print(f"      cost: {f['cost']}")
    for c in r["clusters"]:
        print(f"  cluster {c['kind']} x{c['size']} (J {c['similarity_min']}..{c['similarity_max']}):"
              f" {', '.join(c['ids'])}")
        print(f"      skeleton: {c['skeleton']}")
    for g in r["persona_groups"]:
        print(f"  bio frame group x{g['size']}: {', '.join(g['ids'])}")
        print(f"      frame: {g['skeleton']}")
    print(f"  scope: {r['scope']}")


def cmd_campaign(args):
    try:
        items = _load(args.file)
        report = campaign.analyze(items, platform=args.platform,
                                  cluster_threshold=args.threshold,
                                  frame_threshold=args.frame_threshold)
    except (OSError, ValueError) as exc:
        print(f"[articulate] {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        _print_summary(report)
    return 0


def register(sub):
    p = sub.add_parser("campaign", help="promo-template, persona-bio and cluster signals "
                                         "over a JSON list of short texts")
    p.add_argument("file", help="JSON list of texts or {id, text, kind, platform}; - for stdin")
    p.add_argument("--platform", default="generic", choices=campaign.PLATFORMS)
    p.add_argument("--json", action="store_true", help="print the full report as JSON")
    p.add_argument("--threshold", type=float, default=0.5,
                   help="shingle Jaccard similarity that joins two posts (default 0.5)")
    p.add_argument("--frame-threshold", type=float, default=0.6,
                   help="similarity that joins two bio frames (default 0.6)")
    p.set_defaults(corpus_handler=cmd_campaign)
