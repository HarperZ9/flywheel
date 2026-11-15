import importlib

import pytest


def guard():
    # Missing implementation is a visible assertion failure in the first red run.
    assert importlib.util.find_spec('articulate.meaning_guard'), 'meaning guard missing'
    return importlib.import_module('articulate.meaning_guard')


@pytest.mark.parametrize('old,new,kind', [
    ('We measured 14 samples.', 'We measured 15 samples.', 'number'),
    ('See https://example.org/a.', 'See https://example.org/b.', 'url'),
    ('The result [12] holds.', 'The result holds.', 'citation'),
    ('The result (Smith, 2025) holds.', 'The result (Jones, 2025) holds.', 'citation'),
    ('Use `run --fast` here.', 'Use `run --slow` here.', 'code'),
    ('She said "keep the data".', 'She said "drop the data".', 'quote'),
    ('She said ‘keep the data’.', 'She said ‘drop the data’.', 'quote'),
    ('We use $x < y$.', 'We use $x > y$.', 'math'),
    ('[Read](./a.md)', '[Read](./b.md)', 'link'),
])
def test_protected_content_refuses_changed_paragraph(old, new, kind):
    result = guard().guard_rewrite(old, new)
    assert result['text'] == old
    assert any(kind in reason for item in result['refused'] for reason in item['reasons'])


def test_guard_accepts_safe_paragraph_and_retains_unsafe_one():
    result = guard().guard_rewrite('We really measured 14 samples.\n\nWe really wait.',
                                   'We measured 15 samples.\n\nWe wait.')
    assert result['text'] == 'We really measured 14 samples.\n\nWe wait.'
    assert len(result['refused']) == 1


def test_resegmentation_cannot_bypass_guard():
    old = 'We measured 14 samples.\n\nThe count matters.'
    result = guard().guard_rewrite(old, 'We measured 15 samples. The count matters.')
    assert result['text'] == old
    assert result['refused']


def test_protected_order_cannot_change():
    old = 'We measured 14 successes and 3 failures.'
    assert guard().guard_rewrite(old, 'We measured 3 successes and 14 failures.')['text'] == old


def test_math_and_html_mask_restoration_and_corruption():
    g = guard()
    original = '<p>We really use $x < y$.</p>'
    masked, masks = g.mask_text(original, is_html=True, is_tex=True)
    assert '$x < y$' not in masked
    assert '<p>' not in masked
    assert masks
    good = g.restore_masks(original, masked.replace('really ', ''), is_html=True, is_tex=True)
    assert good['text'] == '<p>We use $x < y$.</p>'
    bad = g.restore_masks(original, masked.replace(masks[0]['token'], ''), is_html=True, is_tex=True)
    assert bad['text'] == original
    assert bad['refused']


def test_cross_paragraph_masks_cannot_be_moved():
    g = guard()
    old = 'We use $x$.\n\nWe use $y$.'
    masked, masks = g.mask_text(old, is_tex=True)
    candidate = masked.replace(masks[0]['token'], 'TEMP').replace(masks[1]['token'], masks[0]['token']).replace('TEMP', masks[1]['token'])
    assert g.restore_masks(old, candidate, is_tex=True)['text'] == old


@pytest.mark.parametrize('old,new', [
    ('The sample weighed 3kg.', 'The sample weighed 4kg.'),
    ('See https://en.wikipedia.org/wiki/Name_(thing).', 'See https://en.wikipedia.org/wiki/Name_(other).'),
    ('See https://example.org/name(foo)bar.', 'See https://example.org/name(foo)baz.'),
    ('<p title="a > b">Wait.</p>', '<p title="a > c">Wait.</p>'),
    ('<a title="a > b" href=/old>Wait.</a>', '<a title="a > b" href=/new>Wait.</a>'),
])
def test_protected_boundaries_cannot_hide_content_changes(old, new):
    assert guard().guard_rewrite(old, new, is_html=True)['text'] == old


def test_raw_restored_submission_is_accepted():
    old = '<p>We really use $x$.</p>'
    assert guard().restore_masks(old, '<p>We use $x$.</p>', is_html=True, is_tex=True)['text'] == '<p>We use $x$.</p>'


def test_raw_restored_submission_still_rejects_changed_math():
    old = '<p>We use $x$.</p>'
    assert guard().restore_masks(old, '<p>We use $y$.</p>', is_html=True, is_tex=True)['text'] == old


@pytest.mark.parametrize('old,new', [
    ('The sample weighed 3kg.', 'The sample weighed 3mg.'),
    ('The sample weighed 3 kg.', 'The sample weighed 3 mg.'),
    ('See [the guide][safe].\n\n[safe]: /a\n[evil]: /b', 'See [the guide][evil].\n\n[safe]: /a\n[evil]: /b'),
    ('> We never share data.', '> We always share data.'),
])
def test_quantity_reference_and_blockquote_are_protected(old, new):
    assert guard().guard_rewrite(old, new)['text'] == old


@pytest.mark.parametrize('old,new', [
    ('Read [manual](./foo(bar).md).', 'Read [manual](./foo(bar).exe).'),
    ('<script>const s = "</code>"; allowAccess = false;</script>', '<script>const s = "</code>"; allowAccess = true;</script>'),
    ('    run --dry-run\n\nDone.', '    run --execute\n\nDone.'),
])
def test_nested_links_opaque_html_and_indented_code_are_protected(old, new):
    assert guard().guard_rewrite(old, new, is_html=True)['text'] == old


@pytest.mark.parametrize('old,new', [
    ('See [safe].\n\n[safe]: /a\n[evil]: /b', 'See [evil].\n\n[safe]: /a\n[evil]: /b'),
    ('See [safe][].\n\n[safe]: /a\n[evil]: /b', 'See [evil][].\n\n[safe]: /a\n[evil]: /b'),
    ('> We keep data\nand never share it.', '> We keep data\nand always share it.'),
])
def test_shortcut_links_and_lazy_quote_continuations_are_protected(old, new):
    assert guard().guard_rewrite(old, new)['text'] == old


# Wave 2, W2-B: a model rewrite that reorders a date, changes a number or adds
# a writing device is refused with a reason, and the CLI says why it kept text.

def test_reordered_date_is_refused_with_a_reason():
    from articulate.meaning_guard import guard_rewrite
    out = guard_rewrite("The board met on 3 May 2026 to vote.\n",
                        "The board met on May 3, 2026 to vote.\n")
    assert out["text"] == "The board met on 3 May 2026 to vote.\n"
    assert any("date" in r for item in out["refused"] for r in item["reasons"])


def test_changed_number_is_refused():
    from articulate.meaning_guard import guard_rewrite
    out = guard_rewrite("We tested 14 models.\n", "We tested 15 models.\n")
    assert out["text"] == "We tested 14 models.\n"
    assert out["refused"]


def test_added_corrective_negation_is_refused():
    from articulate.meaning_guard import guard_rewrite
    original = "The team ships every week and reviews the process.\n"
    rewrite = "The team ships every week. The focus is on process, not features.\n"
    out = guard_rewrite(original, rewrite)
    assert out["text"] == original
    reasons = [r for item in out["refused"] for r in item["reasons"]]
    assert "device introduced: corrective-negation" in reasons


def test_added_detector_device_is_refused():
    from articulate.meaning_guard import guard_rewrite
    original = "The release fixes two bugs.\n"
    rewrite = "Moreover, it is crucial to note that the release fixes two bugs.\n"
    out = guard_rewrite(original, rewrite)
    assert out["text"] == original
    assert any(r.startswith("device introduced:") for item in out["refused"] for r in item["reasons"])


def test_a_device_already_in_the_original_may_stay():
    from articulate.meaning_guard import guard_rewrite
    original = "The focus is on process, not features. We ship weekly.\n"
    rewrite = "The focus is on process, not features. We release weekly.\n"
    assert guard_rewrite(original, rewrite)["text"] == rewrite


def test_removing_a_device_is_accepted():
    from articulate.meaning_guard import guard_rewrite
    original = "Moreover, it is crucial to note that the release fixes two bugs.\n"
    rewrite = "The release fixes two bugs.\n"
    assert guard_rewrite(original, rewrite)["text"] == rewrite


def test_cli_names_why_it_kept_the_original(tmp_path, monkeypatch, capsys):
    from articulate import editor, editing
    path = tmp_path / "draft.md"
    path.write_text("The board met on 3 May 2026 to vote.\n", encoding="utf-8")

    def fake_run_edit(text, **kwargs):
        return {"text": text, "backend": "stub", "model": "stub", "gate_after": "blocked",
                "refused": [{"paragraph": 0, "reasons": ["date protected spans changed"]}],
                "quality_met": False}

    monkeypatch.setattr(editing, "run_edit", fake_run_edit)
    assert editor.polish(str(path), str(tmp_path / "out.md"), 1, 4) == 0
    out = capsys.readouterr().out
    assert "kept the original" in out
    assert "date protected spans changed" in out


def test_cli_reason_when_nothing_was_refused(tmp_path, monkeypatch, capsys):
    from articulate import editor, editing
    path = tmp_path / "draft.md"
    path.write_text("Plain text.\n", encoding="utf-8")
    monkeypatch.setattr(editing, "run_edit", lambda text, **kw: {
        "text": text, "backend": "none", "model": None, "gate_after": "ok", "quality_met": False})
    editor.polish(str(path), str(tmp_path / "out.md"), 1, 4)
    out = capsys.readouterr().out
    assert "kept the original" in out
