"""The interview asks the author questions at locations. It never writes an
answer, never inserts prose, and gives the same questions for the same input."""
import importlib
import re

from voice_fixtures import SCAFFOLD_ESSAY, templated_doc


def interview():
    return importlib.import_module("articulate.interview")


def test_questions_are_deterministic_and_located():
    iv = interview()
    a = iv.questions(SCAFFOLD_ESSAY)
    b = iv.questions(SCAFFOLD_ESSAY)
    assert a == b
    qs = a["questions"]
    assert qs and [q["id"] for q in qs] == [f"q{i}" for i in range(1, len(qs) + 1)]
    for q in qs:
        assert set(q) == {"id", "trigger", "question", "line_start", "line_end", "measure"}
        assert q["question"].endswith("?")
    triggers = {q["trigger"] for q in qs}
    assert {"argued-piece", "high-confidence-claim", "limit-or-unknown", "closing-section"} <= triggers


def test_perspective_and_abstract_triggers_fire_on_a_long_impersonal_draft():
    text = "\n\n".join(templated_doc(i) for i in range(4)) * 2
    triggers = {q["trigger"] for q in interview().questions(text)["questions"]}
    assert {"perspective-stretch", "abstract-run", "scaffold-heavy-section"} <= triggers


def test_markers_are_inert_html_comments_and_add_no_prose():
    iv = interview()
    qs = iv.questions(SCAFFOLD_ESSAY)["questions"]
    marked = iv.mark(SCAFFOLD_ESSAY, qs)
    markers = re.findall(r"<!-- articulate:answer (q\d+) \"([^\"]*)\" -->", marked)
    assert [m[0] for m in markers] == [q["id"] for q in qs]
    stripped = re.sub(r"\n<!-- articulate:answer q\d+ \"[^\"]*\" -->\n", "", marked)
    assert stripped == SCAFFOLD_ESSAY


def test_interview_never_fills_answers_itself():
    """Every marker the interview writes is followed by a blank line or the end
    of the text, so collect finds no answers in a fresh copy, and no question
    carries a first-person claim the document did not contain."""
    iv = interview()
    qs = iv.questions(SCAFFOLD_ESSAY)["questions"]
    marked = iv.mark(SCAFFOLD_ESSAY, qs)
    collected = iv.collect(marked)
    assert collected["answers"] == []
    assert [u["id"] for u in collected["unanswered"]] == [q["id"] for q in qs]
    for q in qs:
        assert not re.search(r"\bI (?:saw|watched|was|did|went|heard|remember)\b", q["question"])
    for line in marked.splitlines():
        if line.startswith("<!-- articulate:answer"):
            assert line.endswith("-->")


def test_collect_round_trips_an_author_answer():
    iv = interview()
    qs = iv.questions(SCAFFOLD_ESSAY)["questions"]
    marked = iv.mark(SCAFFOLD_ESSAY, qs)
    first = re.search(r"<!-- articulate:answer q1 \"[^\"]*\" -->\n", marked)
    answer = "My aunt voted in that county for forty years and never saw a log."
    answered = marked[:first.end()] + answer + "\n" + marked[first.end():]
    out = iv.collect(answered)
    assert out["answers"] == [{"id": "q1", "question": qs[0]["question"], "answer": answer}]
    assert "articulate:answer q1" not in out["text"]
    assert answer in out["text"]
    assert [u["id"] for u in out["unanswered"]] == [q["id"] for q in qs[1:]]


def test_questions_with_a_voice_profile_stay_questions():
    iv = interview()
    from articulate import voice
    from voice_fixtures import VARIED
    profile = voice.build_profile([t for _, _, t in VARIED])
    qs = iv.questions(SCAFFOLD_ESSAY, voice_profile=profile)["questions"]
    assert all(q["question"].endswith("?") for q in qs)


def test_question_text_is_safe_inside_a_comment():
    iv = interview()
    assert "--" not in iv.marker_text("Is this -- \"quoted\"?")
