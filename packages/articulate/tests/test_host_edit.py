import base64
import importlib
import json

import pytest


def host():
    assert importlib.util.find_spec('articulate.host_edit'), 'host protocol missing'
    return importlib.import_module('articulate.host_edit')


def test_host_plan_submit_scripted_good_rewrite():
    h = host()
    text = 'We tested 14 samples — the results are available at https://example.org.'
    plan = h.edit_plan(text, profile='procedure')
    assert plan['findings_before']
    assert all(f['reason'] for f in plan['findings_before'])
    assert plan['instructions'].endswith(importlib.import_module('articulate.prompts').CONTENT_BOUNDARY)
    result = h.edit_submit(text, text.replace(' — ', '. '), plan['plan_id'], model='scripted-host')
    assert result['ok'] is True
    assert result['gate_before'] == 'blocked'
    assert result['gate_after'] == 'ok'
    assert result['receipt']['backend'] == 'host'
    assert result['receipt']['model'] == 'scripted-host'
    assert result['receipt']['attempts'] == []
    assert any(d['delta'] < 0 for d in result['rule_deltas'])


def test_submit_rejects_other_original_and_tampered_settings():
    h = host()
    plan = h.edit_plan('We wait.', profile='procedure')
    with pytest.raises(ValueError, match='plan'):
        h.edit_submit('We changed.', 'We change.', plan['plan_id'])
    encoded, digest = plan['plan_id'].rsplit('.', 1)
    payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    payload['goal'] = 'judge'
    changed = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    with pytest.raises(ValueError, match='plan'):
        h.edit_submit('We wait.', 'We change.', changed + '.' + digest)


def test_plan_pins_ruleset(monkeypatch):
    h = host()
    plan = h.edit_plan('We wait.')
    monkeypatch.setattr(h.detector, 'ruleset_fingerprint', lambda: 'different')
    with pytest.raises(ValueError, match='ruleset'):
        h.edit_submit('We wait.', 'We pause.', plan['plan_id'])


def test_host_bad_number_link_preserved():
    h = host()
    old = 'We tested 14 samples. See https://example.org.'
    plan = h.edit_plan(old)
    out = h.edit_submit(old, 'We tested 15 samples.', plan['plan_id'])
    assert out['text'] == old
    assert out['refused']


@pytest.mark.parametrize('goal', ['fix', 'polish', 'judge'])
def test_deterministic_succeeds_and_reports_its_limits(goal):
    out = host().deterministic_edit('We wait — the record remains.', goal=goal)
    assert out['ok'] is True
    assert out['backend'] == out['receipt']['backend'] == 'none'
    assert out['model'] is None
    assert out['quality_status'] == 'unassessed'
    assert out['instruction']
    if goal == 'judge':
        assert out['text'] == 'We wait — the record remains.'
    else:
        assert '—' not in out['text']


def test_deterministic_preserves_protected_quoted_dash():
    out = host().deterministic_edit('She said "wait — please". We wait — today.')
    assert '"wait — please"' in out['text']


def test_narrative_mode_does_not_rewrite_by_default():
    h = host()
    old = 'We wait — the story remains.'
    assert h.deterministic_edit(old, profile='narrative')['text'] == old


def test_polish_score_regression_retains_original():
    h = host()
    old = 'We wait.'
    plan = h.edit_plan(old, goal='polish')
    before = dict.fromkeys(('concreteness', 'commitment', 'economy', 'rhythm', 'restatable'), 4)
    after = dict(before, economy=3)
    out = h.edit_submit(old, 'We pause.', plan['plan_id'], scores={'before': before, 'after': after})
    assert out['text'] == old
    assert out['quality_status'] == 'regressed'
    assert out['refused']


def test_polish_without_scores_does_not_assert_quality():
    h = host()
    plan = h.edit_plan('We wait.', goal='polish')
    assert h.edit_submit('We wait.', 'We pause.', plan['plan_id'])['quality_status'] == 'unassessed'


def test_invalid_scores_fail_closed():
    h = host()
    plan = h.edit_plan('We wait.', goal='polish')
    with pytest.raises(ValueError, match='scores'):
        h.edit_submit('We wait.', 'We pause.', plan['plan_id'], scores={'before': {}, 'after': {}})


def test_judge_submission_is_assessment_and_never_rewrites():
    h = host()
    plan = h.edit_plan('We wait.', goal='judge')
    out = h.edit_submit('We wait.', 'The actor is clear.', plan['plan_id'])
    assert out['text'] == 'We wait.'
    assert out['assessment'] == 'The actor is clear.'


def test_polish_gate_regression_keeps_original():
    h = host()
    plan = h.edit_plan('We wait.', goal='polish')
    out = h.edit_submit('We wait.', 'We wait — for rain.', plan['plan_id'])
    assert out['text'] == 'We wait.'
    assert out['refused']


def test_shared_prompt_hardening_is_idempotent():
    host()
    prompts = importlib.import_module('articulate.prompts')
    instruction = prompts.rewrite_instructions('no findings')
    assert prompts.hardened(instruction) == instruction


@pytest.mark.parametrize('value', ['10 – 12', '10—12', '10kg – 12kg'])
def test_deterministic_preserves_numeric_range(value):
    old = 'The range is ' + value + '.'
    assert host().deterministic_edit(old)['text'] == old


def test_polish_cannot_accept_changed_text_with_blocked_gate():
    h = host()
    old = 'We wait — for the rain.'
    plan = h.edit_plan(old, goal='polish')
    out = h.edit_submit(old, 'We pause — for the rain.', plan['plan_id'])
    assert out['text'] == old
    assert out['refused']
