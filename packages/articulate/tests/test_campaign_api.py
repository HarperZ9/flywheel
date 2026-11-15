"""Clustering, the analyze() API, the CLI, the published schema, and the bench gates."""
import json
import pathlib

import pytest

from articulate import campaign, campaign_bench, campaign_cluster, cli

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUOTES = [
    "sir... they just dropped a coding model that runs LOCALLY on a laptop at 125 tokens/sec",
    "bro... they just dropped a coding model that runs LOCALLY on an old MacBook at 118 tokens/sec",
    "guys... they just dropped a coding model that runs LOCALLY on a mini PC at 130 tokens/sec",
    "Tried it this morning. Fast, but it hallucinated an import twice.",
    "Does it handle Python type hints well? Our codebase is full of them.",
]


def test_cluster_groups_the_template_and_leaves_organic_replies_out():
    cs = campaign_cluster.cluster(QUOTES)
    assert [c["members"] for c in cs] == [[0, 1, 2]]


def test_cluster_is_deterministic():
    assert campaign_cluster.cluster(QUOTES) == campaign_cluster.cluster(list(QUOTES))


def test_skeleton_shows_the_shared_frame_and_slots():
    sk = campaign_cluster.skeleton(QUOTES[:3])
    assert "they just dropped a coding model that runs locally on {} at {} tokens/sec" in sk[
        "skeleton"]
    assert sk["fillers"][0][0] == "sir..."


def test_character_shingles_work_without_word_boundaries():
    texts = ["このモデルはノートPCで速く動きます。おすすめです。",
             "このモデルはノートPCで速く動きます。最高です。", "今日は雨が降っています。"]
    assert [c["members"] for c in campaign_cluster.cluster(texts)] == [[0, 1]]


def test_exact_copies_are_near_duplicates():
    r = campaign.analyze([QUOTES[0], QUOTES[0] + " ", QUOTES[3]])
    assert r["clusters"][0]["kind"] == "near_duplicate"


def test_report_has_every_schema_field():
    schema = json.loads((ROOT / "docs" / "campaign-schema.json").read_text(encoding="utf-8"))
    r = campaign.analyze(QUOTES + [{"id": "b", "kind": "bio", "text": "Age 42, passionate "
                                    "about Origami. Crypto is the future. | Cat person."}])
    assert r["format"] == schema["properties"]["format"]["const"]
    assert set(schema["required"]) <= set(r)
    item_req = schema["$defs"]["item"]["required"]
    assert all(set(item_req) <= set(i) for i in r["items"])
    assert set(schema["$defs"]["cluster"]["required"]) <= set(r["clusters"][0])
    finding_req = schema["$defs"]["finding"]["required"]
    assert all(set(finding_req) <= set(f) for i in r["items"] for f in i["findings"])


@pytest.mark.parametrize("bad", [{"text": "x"}, [1], [{"id": "a"}], [{"text": "x", "kind": "dm"}],
                                 [{"text": "x", "platform": "myspace"}]])
def test_bad_input_raises_a_value_error(bad):
    with pytest.raises(ValueError):
        campaign.analyze(bad)


def test_cli_json_round_trip(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(QUOTES), encoding="utf-8")
    assert cli.main(["campaign", str(p), "--json", "--platform", "x"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["platform"] == "x" and r["summary"]["posts_in_clusters"] == 3


def test_cli_rejects_unreadable_input(tmp_path, capsys):
    p = tmp_path / "in.json"
    p.write_text("{not json", encoding="utf-8")
    assert cli.main(["campaign", str(p)]) == 2


@pytest.mark.parametrize("split", ["dev", "heldout"])
def test_bench_meets_targets_and_fairness_bound(split):
    r = campaign_bench.run(split)
    assert r["passed"], r
    for kind in ("post", "bio"):
        f = r[kind]["fairness"]
        assert f["passed"] and {"esl", "non_english", "code_switched", "dialect"} <= set(
            f["strata"])


def test_every_control_fails_the_targets():
    ctl = campaign_bench.controls(campaign_bench.campaign_corpus.items())
    assert ctl and all(ctl.values()), ctl


def test_fairness_bound_trips_when_one_stratum_is_over():
    by = {"a": {"fpr": 0.0, "negatives": 10, "fpr_ci": [0, 0.3]},
          "b": {"fpr": 0.3, "negatives": 10, "fpr_ci": [0.1, 0.6]}}
    assert not campaign_bench.fairness(by, 0.15)["passed"]
