"""voice apply: shape the user's own draft toward their measured habits.

It runs only when the user asks, names the profile, and attests the draft is
their own writing (--authored-by-me, or authored_by_user true over MCP). The
profile must belong to this computer's voice identity. The plan binds the
profile's name and hash (articulate/edit-plan/v2), the instructions carry the
profile's plain-sentence description as data, and submit refuses the rewrite
when the profile changed after planning.

The meaning guard runs as for any host edit, with the first-person check and
disclosure spans. Before and after, submit reports how many measured features
sit outside the user's range. Those counts never decide acceptance, and nothing
loops on them.

In apply the profile's aggregate sentences enter the host conversation, because
the host model writes the rewrite. Sample text never does: the profile holds
none.
"""
from . import host_edit, voice, voice_identity, voice_register, voice_store

ATTEST = ("voice apply shapes only text that is yours; say so with --authored-by-me "
          "(authored_by_user: true over MCP)")
DISTANCE_LIMIT = ("These counts place the text against your measured range. The author "
                  "decides whether to accept each edit.")


def _owned(name, directory):
    profile = voice_store.load(name, directory)
    voice_identity.check_owner(profile, directory)
    return profile


def plan(text, name, *, authored_by_user, directory=None, author_text=None, goal="fix"):
    """A v2 host edit plan whose instructions describe the user's voice."""
    if authored_by_user is not True:
        raise ValueError(ATTEST)
    if not isinstance(text, str):
        raise ValueError("voice apply needs the draft text")
    profile = _owned(name, directory)
    bound = {"name": name, "sha256": voice_identity.profile_sha256(profile),
             "notes": voice.describe(profile)}
    out = host_edit.edit_plan(text, goal=goal, author_text=author_text, voice=bound)
    out["voice_name"] = name
    out["voice_profile_sha256"] = bound["sha256"]
    return out


def _outside(report):
    return sum(1 for f in report["features"] if f["verdict"] != "inside")


def distances(before_text, after_text, profile):
    """Feature verdicts before and after, as counts and per-feature rows."""
    before, after = voice.compare(before_text, profile), voice.compare(after_text, profile)
    rows = [{"feature": b["feature"], "before": b["verdict"], "after": a["verdict"]}
            for b, a in zip(before["features"], after["features"])]
    return {"outside_before": _outside(before), "outside_after": _outside(after),
            "features": rows, "scope": DISTANCE_LIMIT}


def check_bound_profile(text, plan_id, directory=None):
    """(settings, profile or None). Raises when a bound profile changed."""
    settings = host_edit.plan_settings(text, plan_id)
    if settings.get("voice_profile_sha256") is None:
        return settings, None
    profile = _owned(settings["voice_name"], directory)
    if voice_identity.profile_sha256(profile) != settings["voice_profile_sha256"]:
        raise ValueError("the voice profile changed after planning; request a new plan")
    return settings, profile


def submit(text, rewrite, plan_id, *, directory=None, author_text=None,
           author_text_origin=None, scores=None, model=None, accept_register_change=False):
    """Guarded result of a voice plan, with voice counts before and after.

    The draft is the user's own, so the register guard runs: a rewrite that
    loses a register feature keeps the original text unless the author passes
    accept_register_change=True."""
    settings, profile = check_bound_profile(text, plan_id, directory)
    out = host_edit.edit_submit(text, rewrite, plan_id, scores=scores, model=model,
                                author_text=author_text, author_text_origin=author_text_origin)
    if "register" not in out:
        refused, quality = out["refused"], out["quality_status"]
        out = voice_register.guard(text, out, lambda reason: host_edit._result(
            text, text, settings, refused + [reason], "host", model, quality, scores,
            author_text_origin, []), accept=accept_register_change)
    if profile is not None:
        out["voice"] = distances(text, out["text"], profile)
    return out
