"""Change kinds an edit may accept, and terms an edit must keep.

The meaning guard retains a paragraph when a protected span or a claim feature
changes. A caller who wants a rewrite to update a number or a link names that
kind in allow_change. The accepted change is then listed in allowed_changes in
the result and in the editor receipt; it is never accepted in silence.

Some kinds can never be allowed. A disclosure of AI assistance and a
first-person sentence the author never wrote protect the author, and HTML and
math hold the document's structure. Requesting one of them is an error that
names the kinds that can be allowed.

Freeze terms are words that must survive every rewrite unchanged, such as a
product name. The guard reads them as protected spans of kind term.

Standard library only.
"""

ALLOWABLE = ('citation', 'code', 'link', 'modal', 'negation', 'number',
             'number-range', 'quantity', 'quote', 'scope', 'term', 'url')
NEVER = ('added-first-person', 'disclosure', 'html', 'math')
_MAX_TERMS = 200
_MAX_TERM_CHARS = 200


def _names(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(',') if part.strip()]
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return [v.strip() for v in value if v.strip()]
    raise ValueError('allow_change must be a list of kind names')


def parse_allow(value):
    """The sorted, de-duplicated kinds in value (a list or a comma-separated string)."""
    kinds = _names(value)
    for kind in kinds:
        if kind not in ALLOWABLE:
            why = 'can never be allowed' if kind in NEVER else 'is not a change kind'
            raise ValueError('allow_change: %r %s; allowable kinds: %s'
                             % (kind, why, ', '.join(ALLOWABLE)))
    return sorted(set(kinds))


def parse_freeze(value):
    """The sorted, de-duplicated freeze terms in value (a list of strings)."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or not all(isinstance(t, str) for t in value):
        raise ValueError('freeze_terms must be a list of strings')
    terms = sorted({t.strip() for t in value if t.strip()})
    if len(terms) > _MAX_TERMS or any(len(t) > _MAX_TERM_CHARS for t in terms):
        raise ValueError('freeze_terms: at most %d terms of at most %d characters'
                         % (_MAX_TERMS, _MAX_TERM_CHARS))
    return terms


def extend_settings(settings, allow_change=None, freeze_terms=None, schema='articulate/edit-plan/v3'):
    """Return plan settings that bind the allowed kinds and freeze terms. With
    neither set, the settings are returned unchanged, so a plan id stays as it was."""
    allow, freeze = parse_allow(allow_change), parse_freeze(freeze_terms)
    if not allow and not freeze:
        return settings
    return dict(settings, schema=schema, allow_change=allow, freeze_terms=freeze)


def instruction_note(settings):
    """A plain note for the rewrite instructions, or '' when the plan binds neither."""
    note = ''
    if settings.get('freeze_terms'):
        note += ('\n\nKeep these terms exactly as written: '
                 + '; '.join(settings['freeze_terms']) + '.')
    if settings.get('allow_change'):
        note += ('\n\nThese kinds of protected content may change where the edit needs it: '
                 + ', '.join(settings['allow_change'])
                 + '. Each such change is reported to the user.')
    return note


def bound(settings):
    """(allow, freeze) bound in verified plan settings, checked again so a
    hand-built plan cannot carry a kind that can never be allowed."""
    allow = parse_allow(settings.get('allow_change'))
    freeze = parse_freeze(settings.get('freeze_terms'))
    if allow != settings.get('allow_change', []) or freeze != settings.get('freeze_terms', []):
        raise ValueError('invalid plan settings')
    return frozenset(allow), tuple(freeze)
