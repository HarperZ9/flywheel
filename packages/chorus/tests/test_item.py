from chorus.item import DiscourseItem, normalize


def test_normalize_maps_comment_rows_and_reads_engagement():
    rows = [
        {"kind": "metadata", "id": "vid1", "ref": "vid1", "text": "{}", "meta": {}},
        {"kind": "comment", "id": "c1", "ref": "vid1", "text": "great talk",
         "meta": {"author": "a", "like_count": 12, "parent": None, "ts": 5.0}},
    ]
    items = normalize(rows)
    assert len(items) == 1                      # metadata row skipped
    it = items[0]
    assert isinstance(it, DiscourseItem)
    assert (it.id, it.source, it.responds_to) == ("c1", "video", "vid1")
    assert it.text == "great talk" and it.author == "a"
    assert it.engagement == 12 and it.ts == 5.0
    assert it.meta.get("engagement_present") is True


def test_normalize_records_absent_engagement_as_zero_not_fabricated():
    rows = [{"kind": "comment", "id": "c2", "ref": "p9", "text": "hi", "meta": {"author": "b"}}]
    it = normalize(rows)[0]
    assert it.engagement == 0
    assert it.meta.get("engagement_present") is False
