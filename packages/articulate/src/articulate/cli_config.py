"""Project config on the command line: profile resolution and `articulate config`.

  articulate config [PATH] [--config PATH|none] [--json]

prints which `.articulate.json` applies to PATH, the profile chosen for it and
why, the terminology rules, the freeze terms and the rule-pack options. The
other commands call `resolve`, `make_receipt` and `edit_options` here so the
core command line only registers `--config`.
"""
import json
import sys

from . import profiles, project, receipt


def add_argument(parser):
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="a .articulate.json project config, or 'none' to turn "
                             "discovery off (default: the nearest one above the file)")


def resolve(name, text, args):
    """(label, profile dict) for a checked file, with the project rules applied."""
    cfg = project.for_path(name, getattr(args, "config", None))
    return project.resolve(name, text, profile=getattr(args, "profile", None),
                           mode=getattr(args, "mode", None), cfg=cfg)


def shown(finding):
    """A finding's category in check text, or its rule id for a terminology rule."""
    return finding["rule_id"] if finding["category"] == "terminology" else finding["category"]


def make_receipt(name, text, args, redact=None, reviewer=None):
    """A receipt under the file's profile and project config, or None after
    printing why the profile or config cannot be used. A receipt names a
    profile, so a --mode is not consulted, as before project configs existed."""
    try:
        cfg = project.for_path(name, getattr(args, "config", None))
        label, _prof = project.resolve(name, text, profile=args.profile, cfg=cfg)
        return receipt.make_receipt(text, label, per_span=getattr(args, "spans", False),
                                    redact=redact, reviewer=reviewer, config=cfg)
    except profiles.ProfileError as e:
        print("[articulate] %s" % e, file=sys.stderr)
        return None


def edit_options(args, text, profile_name):
    """The mode, profile and freeze terms for an edit. With no config this is
    the name-based call the editor made before; project rules travel as a
    profile dict, so the plan binds them."""
    cfg = project.for_path(args.file, getattr(args, "config", None))
    if cfg is None:
        return {"mode": args.mode, "profile": None if args.mode else profile_name}
    name, prof = project.resolve(args.file, text, profile=args.profile, mode=args.mode, cfg=cfg)
    if project.rules_payload(cfg):
        out = {"mode": None, "profile": prof}
    else:
        out = {"mode": args.mode, "profile": None if args.mode else prof}
    if cfg.freeze:
        out["freeze_terms"] = list(cfg.freeze)
    return out


def _info(path, override):
    cfg = project.for_path(path, override)
    name, why = project.choose(path, "", cfg=cfg)
    term = cfg.terminology if cfg else {}
    return {"file": path, "config": cfg.path if cfg else None,
            "profile": name, "profile_source": why,
            "terminology": {"banned": [b["term"] for b in term.get("banned", [])],
                            "preferred": [{"use": p["use"], "instead_of": p["instead_of"]}
                                          for p in term.get("preferred", [])],
                            "allowed": list(term.get("allowed", []))},
            "freeze": list(cfg.freeze) if cfg else [],
            "options": cfg.options if cfg else {}}


def cmd_config(args):
    try:
        info = _info(args.path, args.config)
        project.resolve(args.path, "", cfg=project.for_path(args.path, args.config))
    except project.ConfigError as e:
        print("[articulate] %s" % e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    print("[config] file: %s" % info["file"])
    print("[config] config: %s" % (info["config"] or "none found"))
    print("[config] profile: %s (%s)" % (info["profile"], info["profile_source"]))
    term = info["terminology"]
    print("[config] banned terms: %s" % (", ".join(term["banned"]) or "none"))
    print("[config] preferred terms: %s" % (", ".join(
        "%s for %s" % (p["use"], ", ".join(p["instead_of"])) for p in term["preferred"]) or "none"))
    print("[config] allowed terms: %s" % (", ".join(term["allowed"]) or "none"))
    print("[config] freeze terms: %s" % (", ".join(info["freeze"]) or "none"))
    print("[config] pack options: %s" % (json.dumps(info["options"], sort_keys=True)
                                        if info["options"] else "none"))
    return 0


def register(sub):
    p = sub.add_parser("config", help="show the project config that applies to a file")
    p.add_argument("path", nargs="?", default=".", help="a file or directory (default: .)")
    add_argument(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(corpus_handler=cmd_config)
