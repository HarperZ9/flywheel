"""The closed-list phrase pass behind `fix --backend none`.

Each phrase edit from house_edits is tried alone and kept only when the meaning
guard accepts it. kept_edits drops any edit in a paragraph that the final guard
returned to the original.
"""
from . import house_edits
from .meaning_guard import _PARAGRAPH, guard_rewrite, protected_spans


def _paragraph_of(text, offset):
    return len(_PARAGRAPH.findall(text, 0, offset))


def phrase_pass(text, is_html, is_tex, allow, freeze):
    """Apply each closed-list phrase edit alone, kept only if the meaning guard
    accepts it. Returns the text, the kept edits and the refusals."""
    spans = protected_spans(text, is_html, is_tex, freeze)
    current, kept, refused = text, [], []
    for e in reversed(house_edits.phrase_edits(text, spans)):
        trial = current[:e['start']] + e['new'] + current[e['end']:]
        guarded = guard_rewrite(current, trial, is_html, is_tex, allow=allow, freeze=freeze)
        if guarded['refused']:
            refused += [dict(r, paragraph=_paragraph_of(text, e['start'])) for r in guarded['refused']]
            continue
        current = trial
        kept.append({'rule': 'phrase', 'line': text.count('\n', 0, e['start']) + 1,
                     'start': e['start'], 'end': e['end'], 'old': text[e['start']:e['end']], 'new': e['new']})
    return current, kept[::-1], refused


def kept_edits(text, edits, refused):
    """Drop edits in any paragraph the final guard kept as the original."""
    lost = {r.get('paragraph') for r in refused}
    if None in lost:
        return []
    return [e for e in edits if _paragraph_of(text, e['start']) not in lost]
