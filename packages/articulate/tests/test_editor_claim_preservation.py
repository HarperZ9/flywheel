"""Regressions at the editor acceptance boundary, without model calls."""
import json

import pytest

from articulate.host_edit import edit_plan, edit_submit
from articulate.meaning_guard import guard_rewrite


@pytest.mark.parametrize('original,candidate,kind', [
    ('The treatment may reduce symptoms.', 'The treatment reduces symptoms.', 'modal'),
    ('The treatment reduces symptoms.', 'The treatment may reduce symptoms.', 'modal'),
    ('The client must retry.', 'The client should retry.', 'modal'),
    ('Some requests succeed.', 'All requests succeed.', 'scope'),
    ('Only local files are read.', 'Local files are read.', 'scope'),
    ('We processed at most 10 requests.', 'We processed at least 10 requests.', 'scope'),
    ('The treatment did not reduce symptoms.', 'The treatment reduced symptoms.', 'negation'),
    ('The treatment reduced symptoms.', 'The treatment did not reduce symptoms.', 'negation'),
    ("The client didn't retry.", 'The client retried.', 'negation'),
    ('The client didn’t retry.', 'The client retried.', 'negation'),
    ("The client can't retry.", 'The client can retry.', 'negation'),
])
def test_host_submission_retains_changed_claim(original, candidate, kind):
    # Removing the shared lexical check would falsely accept these candidates.
    result = edit_submit(original, candidate, edit_plan(original)['plan_id'])
    assert result['text'] == original
    assert result['refused'][0]['paragraph'] == 0
    assert any(kind in reason for reason in result['refused'][0]['reasons'])
    diagnostics = json.dumps({'refused': result['refused'], 'receipt': result['receipt']})
    assert original not in diagnostics
    assert candidate not in diagnostics
    assert 'symptoms' not in diagnostics
    assert 'retry' not in diagnostics


@pytest.mark.parametrize('original,candidate', [
    ('The treatment may really reduce symptoms.', 'The treatment may reduce symptoms.'),
    ('Some requests really succeed.', 'Some requests succeed.'),
    ("The client didn't really retry.", 'The client did not retry.'),
    ('The client can’t really retry.', 'The client cannot retry.'),
    ('We processed fewer than 10 requests.', 'We processed under 10 requests.'),
])
def test_host_submission_accepts_rewording_with_preserved_qualifiers(original, candidate):
    result = edit_submit(original, candidate, edit_plan(original)['plan_id'])
    assert result['text'] == candidate
    assert result['refused'] == []


def test_changed_claim_retains_only_affected_paragraph():
    original = 'We may retry.\n\nWe really wait.\n\nSome requests succeed.'
    candidate = 'We retry.\n\nWe wait.\n\nAll requests succeed.'
    result = guard_rewrite(original, candidate)
    assert result['text'] == 'We may retry.\n\nWe wait.\n\nSome requests succeed.'
    assert [item['paragraph'] for item in result['refused']] == [0, 2]


def test_qualifier_cannot_be_moved_to_another_paragraph():
    original = 'We may retry.\n\nWe wait.'
    result = guard_rewrite(original, 'We retry.\n\nWe may wait.')
    assert result['text'] == original
    assert [item['paragraph'] for item in result['refused']] == [0, 1]


@pytest.mark.parametrize('masked', [False, True])
def test_html_and_math_masks_keep_the_visible_claim_guard(masked):
    original = '<p>We may use $x$.</p>\n\n<p>We really wait.</p>'
    plan = edit_plan(original, is_html=True, is_tex=True)
    source = plan['masked_text'] if masked else original
    candidate = source.replace('may ', '').replace('really ', '')
    result = edit_submit(original, candidate, plan['plan_id'])
    assert result['text'] == '<p>We may use $x$.</p>\n\n<p>We wait.</p>'
    assert [item['paragraph'] for item in result['refused']] == [0]


@pytest.mark.parametrize('opaque', [
    '<script>may not;\n\nall = true;</script>',
    '<style>may { all: unset; }\n\nnot {}</style>',
    '<pre>may not\n\nall</pre>',
    '<code>may not\n\nall</code>',
    '<!-- may not\n\nall -->',
])
def test_opaque_html_is_preserved_while_prose_is_edited(opaque):
    original = opaque + '<p title="may not all > some">We really wait.</p>'
    candidate = original.replace('really ', '')
    result = edit_submit(original, candidate, edit_plan(original, is_html=True)['plan_id'])
    assert result['text'] == candidate
    assert result['refused'] == []


def test_html_tag_name_does_not_supply_a_scope_qualifier():
    # The tag named "no" must not turn nearby "may" into a negated modal.
    original = 'We <no>may really wait.</no>'
    candidate = 'We <no>really may wait.</no>'
    result = guard_rewrite(original, candidate, is_html=True)
    assert result['text'] == candidate
    assert result['refused'] == []


@pytest.mark.parametrize('container', [
    '```text\nexample\n\nexample\n```',
    '~~~text\nexample\n\nexample\n~~~',
    '$$x = y\n\nx = y$$',
    '"example\n\nexample"',
    r'\begin{equation}' + '\nx = y\n\nx = y\n' + r'\end{equation}',
])
@pytest.mark.parametrize('claim,candidate', [
    ('The treatment may reduce symptoms.', 'The treatment reduces symptoms.'),
    ('The treatment did not reduce symptoms.', 'The treatment reduced symptoms.'),
    ('Some requests succeed.', 'All requests succeed.'),
])
def test_multiline_container_cannot_hide_the_following_claim(container, claim, candidate):
    original = container + '\n' + claim
    result = edit_submit(original, container + '\n' + candidate, edit_plan(original)['plan_id'])
    assert result['text'] == original
    assert result['refused']


def test_multiline_code_keeps_safe_edit_outside_the_affected_paragraph():
    original = '```text\nexample\n\nexample\n```\nWe may retry.\n\nWe really wait.'
    candidate = original.replace('may ', '').replace('really ', '')
    result = edit_submit(original, candidate, edit_plan(original)['plan_id'])
    assert result['text'] == '```text\nexample\n\nexample\n```\nWe may retry.\n\nWe wait.'
    assert [item['paragraph'] for item in result['refused']] == [1]
