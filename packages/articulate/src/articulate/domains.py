"""Domain profiles: a register profile plus rule packs for one kind of writing.

A domain profile starts from a register profile in articulate.profiles and
adds rule packs (articulate.rules_ext) that run after the detector. The
detector and the register profiles stay as published, so `normative-spec`
keeps its findings, and the RFC keyword rules run only under `rfc-keywords`.

  ux-microcopy        UI strings: length, case, vague errors, link text. Strict.
  code-review         review comments: condescension, absolutes, requests with
                      no reason. Flavored, so the pack reports and the banned
                      devices still gate.
  plain-language      reading grade, long sentences, wordy phrases. Strict.
  controlled-english  sentence length, one instruction per sentence, idioms,
                      phrasal verbs, vague pronouns. Strict. It claims no
                      conformance to ASD-STE100 or any other specification.
  rfc-keywords        the normative-spec register plus RFC 2119 and RFC 8174
                      keyword consistency.
  product-copy        READMEs, release notes and listings read from the user's
                      side: claims point at evidence, the lead says what the
                      tool does for the reader, a mission line exists.
                      Flavored, so these report and the banned devices gate.
  note                a personal note to someone you know: no stock opener and
                      no closing offer (both gate), office words and length
                      reported. Flavored.
  author-voice        the author's own first-person text. Narrative slop, so
                      no device gates; em-dashes are still reported. Literary
                      devices that carry an image, an anchor or a stance pass;
                      an empty one is reported. Claims are still checked
                      against evidence, and edits planned under this profile
                      keep the register (articulate.voice_register) and the
                      author's own terms.
  publication         research and published findings. The research profile
                      plus claim evidence and analogy-map advice: an analogy
                      that carries the argument should point at a testable
                      map. Both report in LOW; neither gates.

  chat                a model's replies in conversation. The published chat
                      register plus the structure pack: anaphora runs,
                      parallel frames, triads, paragraph pinning, parataxis,
                      pointer sentences and landing sentences. Flavored, so
                      the HIGH findings gate.

A domain may carry `gate_promote` (pack categories that gate under a flavored
profile) and `freeze` (terms an edit planned under the profile must keep).

`load_profile(name)` resolves a domain or register profile name, and `load`
also takes a writing mode (a name with a slash). Every place outside the
pinned detector files that resolves a profile name goes through here.
Standard library only.
"""
from . import modes, profiles

_SPEC_KEEP = ("must", "should", "may", "shall", "required", "recommended", "optional")
_REVIEW_KEEP = ("nit", "lgtm", "blocking", "non-blocking", "suggestion")
# The author's own words for his tools (marketing copy uses them; a rewrite keeps them).
AUTHOR_TERMS = ("distill", "distilling", "essence", "layers", "weights", "metamers", "metamer",
                "lens", "boundary", "signal", "noise", "make truth cheap to check")

# name -> base profile, slop override, extra keep terms, register, rule packs.
DOMAINS = {
    "ux-microcopy": {"base": "flavored", "slop": "strict", "keep": (),
                     "register": ("interface", "user", "ui-string"),
                     "rule_packs": ("ux-microcopy",)},
    "code-review": {"base": "flavored", "slop": "flavored", "keep": _REVIEW_KEEP,
                    "register": ("engineering", "peer", "review-comment"),
                    "rule_packs": ("code-review",)},
    "plain-language": {"base": "flavored", "slop": "strict", "keep": (),
                       "register": ("public", "general-reader", "written"),
                       "rule_packs": ("plain-language",)},
    "controlled-english": {"base": "flavored", "slop": "strict", "keep": (),
                           "register": ("technical", "second-language", "written"),
                           "rule_packs": ("controlled-english",)},
    "rfc-keywords": {"base": "normative-spec", "slop": "flavored", "keep": (),
                     "register": None, "rule_packs": ("bcp14",)},
    "product-copy": {"base": "readme", "slop": "flavored", "keep": AUTHOR_TERMS,
                     "register": ("product", "user", "listing"),
                     "rule_packs": ("claims", "product-copy", "privacy"), "freeze": AUTHOR_TERMS},
    "note": {"base": "chat", "slop": "flavored", "keep": (),
             "register": ("personal", "someone-you-know", "note"),
             "rule_packs": ("note", "privacy"), "gate_promote": ("note-opener", "note-closing-offer")},
    "author-voice": {"base": "narrative", "slop": "off", "keep": AUTHOR_TERMS,
                     "register": ("first-person", "reader", "author-voice"),
                     "rule_packs": ("claims", "literary-devices"), "no_em_dash": True,
                     "freeze": AUTHOR_TERMS},
    "publication": {"base": "research", "slop": "flavored", "keep": (),
                    "register": ("findings", "public", "publication"),
                    "rule_packs": ("claims", "analogy-map", "privacy")},
    "outbound": {"base": "chat", "slop": "flavored", "keep": (),
                 "register": ("outbound", "recipient", "message"),
                 "rule_packs": ("privacy",), "gate_promote": ("private-email", "local-path")},
    # The published `chat` register profile, with the structure pack added. The
    # name resolves here first, so the register profile itself stays as published.
    "chat": {"base": "chat", "slop": "flavored", "keep": (), "register": None,
             "rule_packs": ("structure",)},
}


def names():
    return sorted(DOMAINS)


def _domain(name):
    spec = DOMAINS[name]
    out = profiles.load(spec["base"])
    out["slop"] = spec["slop"]
    out["keep"] = tuple(out.get("keep", ())) + tuple(spec["keep"])
    if spec["register"]:
        field, tenor, mode = spec["register"]
        out["register"] = {"field": field, "tenor": tenor, "mode": mode}
    out["rule_packs"] = tuple(spec["rule_packs"])
    if spec.get("gate_promote"):
        out["gate_promote"] = tuple(out.get("gate_promote", ())) + tuple(spec["gate_promote"])
    if "no_em_dash" in spec:
        out["no_em_dash"] = spec["no_em_dash"]
    if spec.get("freeze"):
        out["freeze_terms"] = tuple(spec["freeze"])
    out["domain"] = name
    return out


def load_profile(name):
    """A domain or register profile by name, as a fresh dict."""
    if name in DOMAINS:
        return _domain(name)
    try:
        return profiles.load(name)
    except profiles.ProfileError as exc:
        raise profiles.ProfileError("%s; domain profiles: %s" % (exc, ", ".join(names()))) from None


def load(name):
    """A writing mode (a name with a slash), domain profile or register profile."""
    return modes.load(name) if "/" in str(name) else load_profile(name)

