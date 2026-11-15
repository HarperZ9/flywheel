"""Stateless host editing and deterministic fallback, using only local checks.

The plan token binds content and settings, not caller identity or authority. It
is an integrity checksum, not a signature; callers may generate their own plans.

Plans use schema articulate/edit-plan/v2, which binds the hash of any text the
author supplied (interview answers, for example) so the first-person guard can
accept those sentences and nothing else, and the name and hash of a personal
voice profile when the user asked voice apply to shape their own draft. Plans
under v1 still verify. This module never reads a profile: the caller passes the
profile's hash and its plain-sentence description.

A plan that names change kinds to allow, or terms to freeze, uses schema
articulate/edit-plan/v3: the v2 keys plus sorted allow_change and freeze_terms
lists. A submit reads them from the plan, so it cannot widen what the plan
allowed. A plan with neither stays v2, so its plan id is unchanged.
"""
import base64
from collections import Counter
import hashlib
import hmac
import json
import re

from . import checkext, detector, domains, edit_options, modes, profiles, prompts, voice_register
from .meaning_guard import _PARAGRAPH, guard_rewrite, mask_text, protected_spans, restore_masks
from .edit_notes import _blocking, judge_floor  # noqa: F401  (judge_floor is public here)
from .phrase_pass import kept_edits as _kept_edits, phrase_pass as _phrase_pass


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


PLAN_V1 = 'articulate/edit-plan/v1'
PLAN_V2 = 'articulate/edit-plan/v2'
PLAN_V3 = 'articulate/edit-plan/v3'
_V1_KEYS = frozenset({'schema', 'mode', 'profile', 'goal', 'is_html', 'is_tex', 'ruleset'})
_V2_KEYS = _V1_KEYS | {'author_text_sha256', 'voice_profile_sha256', 'voice_name'}
_PLAN_KEYS = {PLAN_V1: _V1_KEYS, PLAN_V2: _V2_KEYS,
              PLAN_V3: _V2_KEYS | {'allow_change', 'freeze_terms'}}


def _author_hash(author_text):
    if author_text is None:
        return None
    if not isinstance(author_text, str):
        raise ValueError('author_text must be text')
    return 'sha256:' + _hash(author_text)


def _voice_fields(voice):
    if voice is None:
        return None, None
    if not (isinstance(voice, dict) and isinstance(voice.get('name'), str)
            and isinstance(voice.get('sha256'), str) and voice['sha256'].startswith('sha256:')):
        raise ValueError('voice must name a profile and carry its sha256')
    return voice['name'], voice['sha256']


def _settings(mode, profile, goal, is_html, is_tex, author_text=None, voice=None,
              allow_change=None, freeze_terms=None):
    if goal not in ('fix', 'polish', 'judge'):
        raise ValueError('goal must be fix, polish or judge')
    if mode and profile is not None:
        raise ValueError('choose mode or profile, not both')
    prof = modes.load(mode) if mode else (domains.load_profile(profile) if isinstance(profile, str)
                                         else profile if profile is not None else profiles.load(profiles.DEFAULT))
    if not isinstance(prof, dict):
        raise ValueError('profile must be a name or object')
    settings = {'schema': PLAN_V2, 'mode': mode,
                'profile': prof, 'goal': goal, 'is_html': bool(is_html),
                'is_tex': bool(is_tex), 'ruleset': detector.ruleset_fingerprint(),
                'author_text_sha256': _author_hash(author_text),
                'voice_name': _voice_fields(voice)[0],
                'voice_profile_sha256': _voice_fields(voice)[1]}
    # A domain profile's own terms (author-voice, product-copy) are frozen in every plan.
    freeze_terms = edit_options.parse_freeze(freeze_terms) + list(prof.get('freeze_terms', ()))
    settings = edit_options.extend_settings(settings, allow_change, freeze_terms or None, PLAN_V3)
    # Normalize tuples to JSON lists so the digest is stable across processes.
    return json.loads(_canonical(settings))


def _token(text, settings):
    raw = _canonical(settings)
    encoded = base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii').rstrip('=')
    return encoded + '.' + _hash(_canonical({'original': text, 'settings': settings}))


def _verify(text, plan_id):
    try:
        if not isinstance(plan_id, str) or len(plan_id) > 100000:
            raise ValueError('invalid plan token')
        encoded, digest = plan_id.rsplit('.', 1)
        settings = json.loads(base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True))
        if not isinstance(settings, dict) or settings.get('schema') not in _PLAN_KEYS:
            raise ValueError('unknown plan schema')
        if not hmac.compare_digest(_token(text, settings), plan_id):
            raise ValueError('plan does not match original text or settings')
        if settings.get('ruleset') != detector.ruleset_fingerprint():
            raise ValueError('plan ruleset changed; request a new plan')
        if set(settings) != _PLAN_KEYS[settings['schema']] or settings['goal'] not in ('fix', 'polish', 'judge'):
            raise ValueError('invalid plan settings')
        if not isinstance(settings['profile'], dict) or any(type(settings[k]) is not bool for k in ('is_html', 'is_tex')):
            raise ValueError('invalid plan settings')
        edit_options.bound(settings)
        return settings
    except (TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid plan token') from exc


def check_under(text, profile):
    """The local check behind every plan and edit result, rule packs included."""
    return checkext.check_text(text, profile=profile)


def _findings(result):
    return [dict(f, reason=f['label']) for tier in ('high', 'medium', 'low') for f in result[tier]]


def _summary(findings):
    return '\n'.join('L{line} [{tier} {category}] {reason}: {snippet}'.format(**f) for f in findings) or 'No mechanical findings.'


def plan_settings(text, plan_id):
    """The settings a plan binds, after checking the plan matches the text."""
    return _verify(text, plan_id)


def edit_plan(text, mode=None, profile=None, goal='fix', is_html=False, is_tex=False,
              author_text=None, voice=None, allow_change=None, freeze_terms=None):
    settings = _settings(mode, profile, goal, is_html, is_tex, author_text, voice,
                         allow_change, freeze_terms)
    freeze = edit_options.bound(settings)[1]
    voice_notes = voice.get('notes') if voice else None
    before = check_under(text, settings['profile'])
    findings = _findings(before)
    delta = settings['profile'].get('editor', {}).get('standard_delta', '')
    blocking = _summary(_blocking(findings)) if before['gate'] != 'ok' and _blocking(findings) else ''
    instr = (prompts.judge_instructions(_summary(findings), delta, blocking) if goal == 'judge'
             else prompts.rewrite_instructions(_summary(findings), is_html=is_html, standard_delta=delta,
                                               voice_notes=voice_notes))
    instr += edit_options.instruction_note(settings)
    masked, masks = mask_text(text, is_html, is_tex)
    return {'ok': True, 'status': 'host_edit_required', 'backend': 'host', 'model': None, 'attempts': [],
            'goal': goal, 'profile': settings['profile'], 'mode': mode,
            'is_html': bool(is_html), 'is_tex': bool(is_tex), 'plan_id': _token(text, settings),
            'text': text, 'masked_text': masked, 'masks': masks, 'instructions': instr,
            'protected_spans': protected_spans(text, is_html, is_tex, freeze),
            'findings_before': findings, 'gate_before': before['gate'], 'gate': before['gate'],
            'instruction': 'Use these instructions and masked_text to produce a rewrite (or assessment for judge), then call edit_submit with the original text, result and plan_id.',
            'quality_instructions': prompts.quality_instructions() if goal == 'polish' else None,
            'quality_status': 'unassessed',
            'quality_scores_format': {'before': {q: 'integer 1..5' for q in prompts.QUALITIES},
                                      'after': {q: 'integer 1..5' for q in prompts.QUALITIES}} if goal == 'polish' else None,
            'scope': 'Checks that the rewrite keeps every protected span. Read the rewrite to confirm the meaning.'}


def _quality(scores):
    if scores is None:
        return 'unassessed'
    if not isinstance(scores, dict):
        raise ValueError('scores must contain before and after assessments')
    for when in ('before', 'after'):
        if not isinstance(scores.get(when), dict) or any(type(scores[when].get(k)) is not int or not 1 <= scores[when][k] <= 5 for k in prompts.QUALITIES):
            raise ValueError('scores must supply all five integer qualities from 1 to 5 before and after')
    return 'regressed' if any(scores['after'][k] < scores['before'][k] for k in prompts.QUALITIES) else 'host_assessed_no_regression'


def _result(original, accepted, settings, refused, backend, model, quality_status='unassessed', scores=None,
            author_text_origin=None, allowed=None):
    before = check_under(original, settings['profile'])
    after = check_under(accepted, settings['profile'])
    bf, af = _findings(before), _findings(after)
    bc, ac = Counter(f['rule_id'] for f in bf), Counter(f['rule_id'] for f in af)
    deltas = [{'rule_id': rule, 'before': bc[rule], 'after': ac[rule], 'delta': ac[rule] - bc[rule]}
              for rule in sorted(set(bc) | set(ac))]
    receipt = {'schema': 'articulate/editor-receipt/v2', 'backend': backend, 'model': model, 'attempts': [],
               'original_sha256': 'sha256:' + _hash(original), 'text_sha256': 'sha256:' + _hash(accepted),
               'ruleset_version': settings['ruleset'], 'settings': settings,
               'gate_before': before['gate'], 'gate_after': after['gate'], 'rule_deltas': deltas,
               'quality_status': quality_status, 'scores': scores,
               'author_text_sha256': settings.get('author_text_sha256'),
               'voice_profile_sha256': settings.get('voice_profile_sha256'),
               'author_text_origin': author_text_origin,
               'scope': 'Records the gate result before and after the edit and the change in each rule count. The host model supplies the quality scores.'}
    out = {'ok': True, 'text': accepted, 'goal': settings['goal'], 'backend': backend, 'model': model,
           'attempts': [], 'gate_before': before['gate'], 'gate_after': after['gate'], 'gate': after['gate'],
           'findings_before': bf, 'findings_after': af, 'remaining_findings': af,
           'rule_deltas': deltas, 'refused': refused, 'receipt': receipt,
           'quality_status': quality_status, 'scores': scores}
    if settings.get('allow_change'):
        # Allowed changes are reported, in the result and the receipt, never silent.
        out['allowed_changes'] = receipt['allowed_changes'] = list(allowed or [])
    return out


def _check_author_text(settings, author_text):
    bound = settings.get('author_text_sha256')
    if author_text is None and bound is None:
        return
    if bound is None:
        raise ValueError('this plan binds no author text; request a plan with author_text')
    if _author_hash(author_text) != bound:
        raise ValueError('author text does not match the plan')


def edit_submit(text, rewrite, plan_id, scores=None, model=None, author_text=None,
                author_text_origin=None):
    settings = _verify(text, plan_id)
    if author_text_origin not in (None, 'cli-file', 'host-supplied'):
        raise ValueError('author_text_origin must be cli-file or host-supplied')
    if author_text is not None and author_text_origin is None:
        author_text_origin = 'host-supplied'
    if not isinstance(rewrite, str):
        raise ValueError('rewrite must be text')
    _check_author_text(settings, author_text)
    if settings['goal'] == 'judge':
        out = _result(text, text, settings, [], 'host', model, author_text_origin=author_text_origin)
        return judge_floor(out, rewrite)
    allow, freeze = edit_options.bound(settings)
    guarded = restore_masks(text, rewrite, settings['is_html'], settings['is_tex'], author_text,
                            allow=allow, freeze=freeze)
    accepted, refused = guarded['text'], guarded['refused']
    quality = _quality(scores)
    if settings['goal'] == 'polish':
        before = check_under(text, settings['profile'])
        after = check_under(accepted, settings['profile'])
        reasons = []
        if quality == 'regressed':
            reasons.append('quality scores regressed')
        if accepted != text and after['gate'] != 'ok':
            reasons.append('polish candidate detector gate is blocked')
        required = set(settings['profile'].get('editor', {}).get('require_fix', []))
        if required & {f['category'] for f in after['low']} - {f['category'] for f in before['low']}:
            reasons.append('required advisory regressed')
        if reasons:
            accepted = text
            refused.append({'paragraph': None, 'reasons': reasons})
    if refused and quality == 'host_assessed_no_regression':
        quality = 'unassessed_after_guard'
    allowed = guarded.get('allowed_changes', []) if accepted != text else []
    out = _result(text, accepted, settings, refused, 'host', model, quality, scores,
                  author_text_origin, allowed)
    if settings['profile'].get('domain') == 'author-voice':
        out = voice_register.guard(text, out, lambda reason: _result(
            text, text, settings, refused + [reason], 'host', model, quality, scores,
            author_text_origin, []))
    return out


def deterministic_edit(text, mode=None, profile=None, goal='fix', is_html=False, is_tex=False,
                       allow_change=None, freeze_terms=None):
    settings = _settings(mode, profile, goal, is_html, is_tex,
                         allow_change=allow_change, freeze_terms=freeze_terms)
    allow, freeze = edit_options.bound(settings)
    candidate, edits, phrase_refused = text, [], []
    prof = settings['profile']
    if goal != 'judge' and prof.get('slop') != 'off' and prof.get('editor', {}).get('run_fix_by_default', True):
        candidate, edits, phrase_refused = _phrase_pass(text, is_html, is_tex, allow, freeze)
        # Transform only unprotected text. A final common guard also checks the result.
        spans = sorted(protected_spans(candidate, is_html, is_tex, freeze), key=lambda s: (s['start'], -s['end']))
        chunks, end = [], 0
        def transform(prose):
            if prof.get('no_em_dash', True):
                prose = re.sub(r'[ \t]*\u2014[ \t]*|[ \t]+\u2013[ \t]+', ', ', prose)
            # Internal doubled spaces only; indentation and Markdown line breaks stay.
            return re.sub(r'(?<=\S)[ \t]{2,}(?=\S)', ' ', prose)
        for span in spans:
            if span['start'] >= end:
                chunks.extend((transform(candidate[end:span['start']]), candidate[span['start']:span['end']]))
                end = span['end']
        chunks.append(transform(candidate[end:]))
        candidate = ''.join(chunks)
    checked = guard_rewrite(text, candidate, is_html, is_tex, allow=allow, freeze=freeze)
    edits = _kept_edits(text, edits, checked['refused'])
    checked = dict(checked, refused=phrase_refused + checked['refused'])
    if goal == 'polish' and check_under(text, prof)['gate'] == 'ok' and check_under(checked['text'], prof)['gate'] != 'ok':
        checked = {'text': text, 'refused': [{'paragraph': None, 'reasons': ['detector gate regressed']}]}
    out = _result(text, checked['text'], settings, checked['refused'], 'none', None,
                  allowed=checked.get('allowed_changes'))
    # Every closed-list phrase edit that survived the guards, in original offsets.
    out['edits'] = out['receipt']['edits'] = edits
    out['instruction'] = 'For a model edit, use edit_plan/edit_submit or configure a reachable model backend.'
    if goal == 'judge':
        out['assessment'] = _summary(out['findings_before'])
    return out
