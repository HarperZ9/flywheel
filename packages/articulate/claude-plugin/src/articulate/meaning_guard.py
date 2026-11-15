"""Conservative lexical preservation checks, not a proof of semantic equivalence.

Paragraph boundaries and ordered protected spans must survive. If alignment is
ambiguous the whole document is retained; otherwise only affected paragraphs
are retained. No model or network is used here.

Two checks guard the author. A line that discloses AI assistance is a protected
span of kind disclosure, so a rewrite cannot drop or reword it. A rewrite
paragraph that gains a first-person sentence with no source in the original
paragraph or in author-supplied text is retained with reason added-first-person.

A caller may name change kinds it accepts (allow) and terms it freezes
(freeze, protected spans of kind term). An allowed change is reported in
allowed_changes, never accepted in silence. Disclosure, added-first-person,
HTML and math changes cannot be allowed; articulate.edit_options validates the
kinds before they reach this module.

A date is a protected span of kind date, so "3 May" cannot become "May 3". A
rewrite paragraph that adds a writing device the original paragraph lacked (a
HIGH or MEDIUM detector finding, or a corrective negation such as "X, not Y")
is retained with reason "device introduced: <name>". An edit exists to remove
devices, so one that adds a device is refused.
"""
from collections import Counter
import hashlib
import re

from . import meaning
from .invariants import freeze_pattern
from .authorship import disclosure_spans, novel_first_person, strip_supplied


_MATH = re.compile(
    r'\\begin\{(equation|align|gather|multline|eqnarray|split|theorem|lemma|proof|definition|proposition|corollary|claim)\*?\}.*?\\end\{\1\*?\}'
    r'|\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|(?<!\\)\$(?:\\.|[^$\\])*\$', re.S)
_MONTH = (r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?'
          r'|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?')
_DATE = re.compile(r'\b\d{1,2}(?:st|nd|rd|th)?\s+' + _MONTH + r'(?:,?\s+\d{4})?(?!\w)'
                   r'|\b' + _MONTH + r'\s+\d{1,2}(?:st|nd|rd|th)?\b(?:,?\s+\d{4})?'
                   r'|\b\d{4}-\d{2}-\d{2}\b')
# Corrective negation: "X, not Y", "not just X but Y", "isn't X; it's Y".
_CORRECTIVE = re.compile(
    r"(?i),\s+not\s+(?!only\b|just\b|merely\b|least\b|yet\b|always\b|all\b)[a-z]"
    r"|\bnot\s+(?:just|only|merely)\b[^.!?\n]*\bbut\b"
    r"|\b(?:isn|aren|wasn)[’']t\b[^.!?\n]*[,;:—]\s*(?:it|they)[’'](?:s|re)\b")
_TAG_BODY = r'''(?:[^>"']|"[^"]*"|'[^']*')*'''
_HTML = re.compile(r'<!--.*?-->|<(?P<opaque>script|style|pre|code)\b' + _TAG_BODY +
                   r'>.*?</(?P=opaque)\s*>|<![^>]*>|</?[A-Za-z]' + _TAG_BODY + r'>', re.S | re.I)
_PATTERNS = [
    ('code', re.compile(r'```.*?```|~~~.*?~~~|(`+)([^`]|(?!\1)`)*?\1', re.S)),
    ('code', re.compile(r'(?m)^(?: {4}|\t)[^\n]+')),
    ('math', _MATH),
    ('url', re.compile(r'(?:https?://|ftp://|mailto:|www\.)[^\s<>\]"\u201d]+', re.I)),
    # Greedy through the last close parenthesis: conservatively includes nested
    # targets and any intervening same-line prose rather than truncating a URL.
    ('link', re.compile(r'\]\([^\n]*\)|\[[^\]\n]*\]\[[^\]\n]*\]|(?m:^\s*\[[^\]\n]+\]:[^\n]+)')),
    # Bracket text may be a shortcut reference; keep it even when no definition
    # occurs in this paragraph (definitions may appear elsewhere in a document).
    ('link', re.compile(r'\[[^\]\n]+\]')),
    ('citation', re.compile(r'\[(?:\d[^\]\n]*|\^[^\]\n]+|@[^\]\n]+)\]|\\(?:cite\w*|ref|eqref)\*?(?:\[[^\]]*\])?\{[^}]*\}|\([^()\n]*[A-Z][^()\n]*\b(?:19|20)\d{2}[a-z]?[^()\n]*\)')),
    ('quote', re.compile(r'"(?:\\.|[^"\\])*"|\u201c[^\u201d]*\u201d|\u2018[^\u2019]*\u2019|(?<!\w)\x27[^\x27\n]+\x27(?!\w)', re.S)),
    # CommonMark permits lazy continuation without a leading >. Protect the
    # entire quote paragraph, conservatively including such following lines.
    ('quote', re.compile(r'(?m)^[ \t]*>[^\n]*(?:\n(?![ \t]*\r?$)[^\n]+)*')),
    ('date', _DATE),
    ('number', re.compile(r'[+-]?\d+(?:[.,:/\-]\d+)*(?:\s?%|[eE][+-]?\d+)?')),
    ('number-range', re.compile(r'\d+(?:[.,]\d+)*(?:[A-Za-z%]+)?[ \t]*[\u2013\u2014-][ \t]*\d+(?:[.,]\d+)*(?:[A-Za-z%]+)?')),
    ('quantity', re.compile(r'\d+(?:[.,]\d+)*(?:[A-Za-z\u00b5\u03bc\u00b0%]+|[ \t]+(?:kg|mg|g|km|cm|mm|m|ml|mL|L|Hz|kHz|MHz|GHz|ms|s|W|kW|V|A|K|\u00b0C|\u00b0F)\b)')),
]
_PARAGRAPH = re.compile(r'(\r?\n[ \t]*\r?\n(?:[ \t]*\r?\n)*)')
_TOKEN = re.compile(r'\u2983ARTICULATE_[^\u2984]*\u2984')
_CLAIM_KINDS = frozenset(('modal', 'scope', 'negation'))


def protected_spans(text, is_html=False, is_tex=False, freeze=()):
    """Return exact spans; overlaps are intentional (a citation can contain numbers).
    Freeze terms, when given, are spans of kind term."""
    patterns = _PATTERNS + ([('html', _HTML)] if is_html else [])
    term = freeze_pattern(freeze) if freeze else None
    patterns = patterns + ([('term', term)] if term else [])
    spans = [{'kind': kind, 'start': m.start(), 'end': m.end(), 'text': m.group()}
             for kind, pattern in patterns for m in pattern.finditer(text)]
    spans += [{'kind': 'disclosure', 'start': a, 'end': b, 'text': text[a:b]}
              for a, b in disclosure_spans(text)]
    return sorted(spans, key=lambda s: (s['start'], s['end'], s['kind']))


def _signature(text, is_html=False, is_tex=False, freeze=(), allow=frozenset()):
    """Ordered span texts by kind, leaving out the kinds the caller allows."""
    out = {}
    for span in protected_spans(text, is_html, is_tex, freeze):
        if span['kind'] not in allow:
            out.setdefault(span['kind'], []).append(span['text'])
    return out


def _reason_kind(reason):
    """The change kind a refusal reason names, or None for any other reason."""
    for suffix in (' protected spans changed', ' claim features changed'):
        if reason.endswith(suffix):
            return reason[:-len(suffix)]
    return None


def _split_allowed(reasons, allow):
    """(blocking reasons, allowed kinds). Any blocking reason retains the paragraph."""
    blocking = [r for r in reasons if _reason_kind(r) not in allow]
    return blocking, sorted({_reason_kind(r) for r in reasons if _reason_kind(r) in allow})


def _outcome(text, refused, allow, allowed=()):
    out = {'text': text, 'refused': refused}
    if allow:
        out['allowed_changes'] = list(allowed)
    return out


def _refusal(index, reasons):
    return {'paragraph': index, 'reasons': reasons}


def _devices(paragraph):
    """Counts of writing devices in one paragraph: detector rule ids at HIGH and
    MEDIUM, plus corrective negation, which the pinned detector does not name."""
    from .checkext import check_text
    found = check_text(paragraph)
    counts = Counter(f["rule_id"] for key in ("high", "medium") for f in found[key])
    counts["corrective-negation"] += len(_CORRECTIVE.findall(paragraph))
    return counts


def _added_devices(before, after):
    old, new = _devices(before), _devices(after)
    return sorted(name for name, n in new.items() if n > old.get(name, 0))


def _claim_paragraphs(parts, is_html, is_tex):
    """Blank opaque containers globally, then use original paragraph boundaries."""
    # A closing fence in a later paragraph must not become a new opening fence
    # that hides the prose following it. HTML, math and quotes need the same
    # document context. Keep numbers visible for bounds such as "under 10".
    text = ''.join(parts)
    chars = list(text)
    for span in protected_spans(text, is_html, is_tex):
        if span['kind'] not in ('number', 'number-range', 'quantity', 'term'):
            for i in range(span['start'], span['end']):
                if chars[i] not in '\r\n':
                    chars[i] = ' '
    text = ''.join(chars)
    # Newly blank lines must not introduce paragraph boundaries of their own.
    result, offset = [], 0
    for part in parts:
        result.append(text[offset:offset + len(part)])
        offset += len(part)
    return result


def guard_rewrite(original, rewrite, is_html=False, is_tex=False, author_text=None,
                  allow=frozenset(), freeze=()):
    """Retain paragraphs with changed protected spans, lexical claim features, or a
    first-person sentence that neither the original nor the author supplied. A
    change of an allowed kind is accepted and listed in allowed_changes."""
    allow = frozenset(allow)
    if original == rewrite:
        return _outcome(original, [], allow)
    if original.strip() and not rewrite.strip():
        return _outcome(original, [_refusal(None, ['empty rewrite'])], allow)
    old, new = _PARAGRAPH.split(original), _PARAGRAPH.split(rewrite)
    if len(old) != len(new):
        return _outcome(original, [_refusal(None, ['paragraph alignment changed'])], allow)
    # Sentences the author supplied verbatim carry their own spans and claims;
    # they are checked against the author's text, not against the original.
    checked = [strip_supplied(part, author_text, original) for part in new]
    old_prose = _claim_paragraphs(old, is_html, is_tex)
    new_prose = _claim_paragraphs(checked, is_html, is_tex)
    refused, allowed = [], []
    for i in range(0, len(old), 2):
        before = _signature(old[i], is_html, is_tex, freeze)
        after = _signature(checked[i], is_html, is_tex, freeze)
        reasons = [kind + ' protected spans changed' for kind in sorted(set(before) | set(after))
                   if before.get(kind, []) != after.get(kind, [])]
        report = meaning.compare(old_prose[i], new_prose[i], tex=is_tex)
        changed = {item['kind'] for item in meaning.blocking(report)
                   if item['kind'] in _CLAIM_KINDS}
        # The comparison report contains source prose. Only kinds leave this
        # boundary; retain the older ordered guards for exact protected spans.
        reasons.extend(kind + ' claim features changed' for kind in sorted(changed))
        if novel_first_person(old[i], new[i], author_text):
            reasons.append('added-first-person')
        reasons.extend('device introduced: ' + name.split('/')[0]
                       for name in _added_devices(old[i], checked[i]))
        blocking, kinds = _split_allowed(reasons, allow)
        if blocking:
            new[i] = checked[i] = old[i]
            refused.append(_refusal(i // 2, reasons))
        else:
            allowed.extend({'paragraph': i // 2, 'kind': kind} for kind in kinds)
    # A multiline span might cross a paragraph boundary. Recheck the full result,
    # ignoring only the kinds the caller allows.
    candidate = ''.join(new)
    if (_signature(original, is_html, is_tex, freeze, allow)
            != _signature(''.join(checked), is_html, is_tex, freeze, allow)):
        cross = _refusal(None, ['cross-paragraph protected spans changed'])
        return _outcome(original, refused + [cross], allow)
    return _outcome(candidate, refused, allow, allowed)


def mask_text(text, is_html=False, is_tex=False):
    """Mask HTML and math using input-specific tokens that cannot collide with input."""
    spans = [s for s in protected_spans(text, is_html, is_tex)
             if (s['kind'] == 'math' and is_tex) or (s['kind'] == 'html' and is_html)]
    # Long outer spans win over overlapping inner spans.
    spans.sort(key=lambda s: (s['start'], -s['end']))
    selected, end = [], -1
    for s in spans:
        if s['start'] >= end:
            selected.append(dict(s))
            end = s['end']
    prefix = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
    while 'ARTICULATE_' + prefix in text:
        prefix += '_'
    chunks, end = [], 0
    for i, s in enumerate(selected):
        s['token'] = '\u2983ARTICULATE_' + prefix + '_' + str(i) + '\u2984'
        chunks.extend((text[end:s['start']], s['token']))
        end = s['end']
    chunks.append(text[end:])
    return ''.join(chunks), selected


def restore_masks(original, rewrite, is_html=False, is_tex=False, author_text=None,
                  allow=frozenset(), freeze=()):
    """Require each mask once, in its original paragraph and order, before restoring."""
    extra = {'allow': allow, 'freeze': freeze}
    if 'ARTICULATE_' not in rewrite:
        return guard_rewrite(original, rewrite, is_html, is_tex, author_text, **extra)
    masked, masks = mask_text(original, is_html, is_tex)
    if not masks:
        return guard_rewrite(original, rewrite, is_html, is_tex, author_text, **extra)
    old, new = _PARAGRAPH.split(masked), _PARAGRAPH.split(rewrite)
    if len(old) != len(new):
        return _outcome(original, [_refusal(None, ['mask paragraph alignment changed'])], allow)
    refused = []
    for i in range(0, len(old), 2):
        if _TOKEN.findall(old[i]) != _TOKEN.findall(new[i]):
            new[i] = old[i]
            refused.append(_refusal(i // 2, ['mask missing, duplicated, changed or reordered']))
    restored = ''.join(new)
    for s in masks:
        restored = restored.replace(s['token'], s['text'])
    checked = guard_rewrite(original, restored, is_html, is_tex, author_text, **extra)
    checked['refused'] = refused + checked['refused']
    return checked
