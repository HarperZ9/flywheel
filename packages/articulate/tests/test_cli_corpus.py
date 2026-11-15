"""The series and voice verbs on the command line. Nothing is written except to
an explicit --out, --receipt or the voice store."""
import json

from articulate import cli
from voice_fixtures import SCAFFOLD_ESSAY, VARIED, templated_docs


def _write(tmp_path, docs):
    paths = []
    for d in docs:
        p = tmp_path / d["name"]
        p.write_text(d["text"], encoding="utf-8")
        paths.append(str(p))
    return paths


def test_corpus_text_json_and_receipt(tmp_path, capsys):
    paths = _write(tmp_path, templated_docs())
    assert cli.main(["corpus", *paths]) == 0
    assert "corpus/paragraph-scaffold" in capsys.readouterr().out
    assert cli.main(["corpus", *paths, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["findings"]
    rec = tmp_path / "r.json"
    assert cli.main(["corpus", *paths, "--receipt", str(rec)]) == 0
    capsys.readouterr()
    assert cli.main(["verify", str(rec), *paths]) == 0
    assert "Match" in capsys.readouterr().out


def test_corpus_needs_two_files_unless_single(tmp_path, capsys):
    paths = _write(tmp_path, templated_docs()[:1])
    assert cli.main(["corpus", *paths]) == 2
    assert cli.main(["corpus", *paths, "--single"]) == 0


def test_voice_learn_show_list_compare_delete(tmp_path, capsys):
    samples = _write(tmp_path, [{"name": n, "text": t} for n, _, t in VARIED])
    store = str(tmp_path / "store")
    assert cli.main(["voice", "learn", *samples, "--name", "mine", "--mine", "--dir", store]) == 0
    capsys.readouterr()
    assert cli.main(["voice", "show", "mine", "--dir", store]) == 0
    shown = capsys.readouterr().out
    assert "In your samples" in shown and "mine.json" in shown
    assert cli.main(["voice", "list", "--dir", store]) == 0
    assert "mine" in capsys.readouterr().out
    draft = _write(tmp_path, templated_docs()[:1])[0]
    assert cli.main(["voice", "compare", draft, "--name", "mine", "--dir", store]) == 0
    assert "first_person_per_1k" in capsys.readouterr().out
    assert cli.main(["voice", "delete", "mine", "--dir", store]) == 0
    assert "mine.json" in capsys.readouterr().out
    assert not (tmp_path / "store" / "mine.json").exists()


def test_interview_marks_only_to_out_and_collects(tmp_path, capsys):
    doc = tmp_path / "e.md"
    doc.write_text(SCAFFOLD_ESSAY, encoding="utf-8")
    assert cli.main(["interview", str(doc)]) == 0
    assert "q1" in capsys.readouterr().out
    out = tmp_path / "marked.md"
    assert cli.main(["interview", str(doc), "--out", str(out)]) == 0
    assert doc.read_text(encoding="utf-8") == SCAFFOLD_ESSAY
    assert "articulate:answer q1" in out.read_text(encoding="utf-8")
    answers = tmp_path / "answers.txt"
    assert cli.main(["interview", "--collect", str(out), "--answers-out", str(answers)]) == 0
    assert answers.read_text(encoding="utf-8") == ""


def test_restructure_prints_a_diff_and_writes_only_to_out(tmp_path, capsys):
    doc = tmp_path / "e.md"
    doc.write_text(SCAFFOLD_ESSAY, encoding="utf-8")
    assert cli.main(["restructure", str(doc)]) == 0
    assert capsys.readouterr().out.startswith("--- ")
    assert doc.read_text(encoding="utf-8") == SCAFFOLD_ESSAY
    out = tmp_path / "p.md"
    assert cli.main(["restructure", str(doc), "--out", str(out)]) == 0
    assert "## Sources and method" in out.read_text(encoding="utf-8")


def test_titles_from_files_and_answers(tmp_path, capsys):
    paths = _write(tmp_path, templated_docs())
    assert cli.main(["titles", *paths]) == 0
    assert "X is not Y" in capsys.readouterr().out
    answers = tmp_path / "a.txt"
    answers.write_text("how the books hide the cost of the plan\n\n\n\n", encoding="utf-8")
    assert cli.main(["titles", *paths, "--answers", str(answers), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert all(s["label"] == "suggestion" for s in out["suggestions"])


def test_plan_and_submit_accept_author_text(tmp_path, capsys):
    doc = tmp_path / "e.md"
    doc.write_text("Turnout was low across the district this year.", encoding="utf-8")
    author = tmp_path / "a.txt"
    author.write_text("I knocked on doors in that district.", encoding="utf-8")
    assert cli.main(["plan", str(doc), "--author-text", str(author)]) == 0
    plan = json.loads(capsys.readouterr().out)
    rewrite = tmp_path / "r.md"
    rewrite.write_text("Turnout was low across the district this year. "
                       "I knocked on doors in that district.", encoding="utf-8")
    assert cli.main(["submit", str(doc), str(rewrite), "--plan", plan["plan_id"],
                     "--author-text", str(author)]) == 0
    assert "I knocked" in json.loads(capsys.readouterr().out)["text"]
