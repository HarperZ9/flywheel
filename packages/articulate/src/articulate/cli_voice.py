"""Command-line verbs for the personal voice: learn, show, list, path, compare,
apply, submit, export, import, delete and identity, plus intend and check for a
voice built from intent (voice_intent_cli).

The command line is the only writer of the voice store. learn reads only the
files the user names, and only after --mine says they are the user's own
writing. apply and submit never edit the draft in place; they write to --out
or print.
"""
import json
import sys

from . import voice, voice_apply, voice_identity, voice_store
from .detector import binary_reason
from .voice_text import format_compare


def _read(path):
    with open(path, "rb") as fh:
        data = fh.read()
    reason = binary_reason(data, name=path)
    if reason:
        raise ValueError(f"cannot read {path} as text ({reason})")
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


def _emit(value, args, text, out=None):
    body = json.dumps(value, ensure_ascii=False, indent=2) if getattr(args, "json", False) else text
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        print(f"Wrote {out}")
    else:
        print(body)


def _learn(args):
    if not args.mine:
        raise ValueError("voice learn builds a profile only from your own writing; add --mine "
                         "to say these samples are yours")
    samples = [_read(p) for p in args.samples]
    profile = voice.build_profile(samples, vocabulary=not args.no_vocabulary)
    voice_identity.ensure_identity(args.dir)
    path = voice_store.save(voice_identity.bind(profile, args.dir), args.name, args.dir)
    print(f"Saved voice profile {args.name!r} to {path}")
    print("\n".join(voice.describe(profile)))
    return 0


def _owned(args):
    profile = voice_store.load(args.name, args.dir)
    voice_identity.check_owner(profile, args.dir)
    return profile


def _show(args):
    profile = voice_store.load(args.name, args.dir)
    owner = profile.get("owner") or {}
    text = "\n".join(voice.describe(profile)) + (
        f"\n\nOwner: {owner.get('display_name') or owner.get('owner_id', 'none')}"
        f"\nStored at {voice_store.profile_path(args.name, args.dir)}")
    _emit(profile, args, text)
    return 0


def _compare(args):
    profile = _owned(args)
    for path in args.drafts:
        report = voice.compare(_read(path), profile)
        _emit(report, args, f"{path}\n{format_compare(report)}")
    return 0


def _apply(args):
    author = _read(args.author_text) if args.author_text else None
    out = voice_apply.plan(_read(args.draft), args.name, authored_by_user=bool(args.authored_by_me),
                           directory=args.dir, author_text=author)
    _emit(out, args, out["instructions"] + "\n\nplan_id: " + out["plan_id"], args.out)
    return 0


def _submit(args):
    author = _read(args.author_text) if args.author_text else None
    out = voice_apply.submit(_read(args.draft), _read(args.rewrite), args.plan, directory=args.dir,
                             author_text=author, author_text_origin="cli-file" if author else None)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as fh:
            fh.write(out["text"])
    v = out.get("voice", {})
    _emit(out, args, f"Features outside your range: {v.get('outside_before')} before, "
                     f"{v.get('outside_after')} after. {v.get('scope', '')}\n"
                     f"Kept original for {len(out['refused'])} paragraph(s).")
    return 0


def _export(args):
    data = voice_identity.export_profile(args.name, args.dir)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"Exported {args.name!r} to {args.out}. It holds aggregates only, no sample text.")
    return 0


def _import(args):
    with open(args.file, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    path = voice_identity.import_profile(data, args.dir, adopt_identity=args.adopt_identity)
    print(f"Imported to {path}")
    return 0


def _delete(args):
    if args.all:
        removed = voice_identity.delete_all(args.dir)
    elif args.name:
        removed = [voice_store.delete(args.name, args.dir)]
    else:
        raise ValueError("name a profile to delete, or pass --all")
    print("\n".join(f"Deleted {p}" for p in removed) or "Nothing to delete.")
    return 0


def _identity(args):
    ident = (voice_identity.ensure_identity(args.dir, args.display_name) if args.display_name
             else voice_identity.load_identity(args.dir))
    if ident is None:
        print("No voice identity yet. voice learn --mine makes one.")
    else:
        print(f"owner_id: {ident['owner_id']}\ndisplay name: {ident.get('display_name') or '(none)'}"
              f"\nstored at {voice_identity.identity_path(args.dir)}")
    return 0


def _list(args):
    print("\n".join(voice_store.names(args.dir)) or "No voice profiles stored.")
    return 0


def _path(args):
    print(voice_store.store_dir(args.dir))
    return 0


def _intend(args):
    from .voice_intent_cli import intend
    return intend(args)


def _check(args):
    from .voice_intent_cli import check
    return check(args)


def _register(args):
    from .voice_intent_cli import register
    return register(args)


ACTIONS = {"intend": _intend, "check": _check, "register": _register, "learn": _learn, "show": _show, "compare": _compare, "apply": _apply,
           "submit": _submit, "export": _export, "import": _import, "delete": _delete,
           "identity": _identity, "list": _list, "path": _path}


def cmd_voice(args):
    return ACTIONS[args.voice_cmd](args)


def report_error(exc):
    print(f"[articulate] {exc}", file=sys.stderr)
    return 2
