"""Video manifest checks, before an upload.

The manifest is JSON: {"videos": [{"id", "title", "key_phrase", "description",
"hashtags", "sources", "pinned_comment", "shorts_cut"}]}. Chapter rules follow
YouTube's help page on video chapters: the first timestamp is 0:00, there are at
least three, and each runs ten seconds or more.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .report import ERROR, WARN, Report

TITLE_MAX = 70
KEY_PHRASE_WINDOW = 40
LEAD = 150
PARA_BREAK = "\n\n"
STAMP = re.compile(r"^\s*((?:\d{1,2}:)?\d{1,2}:\d{2})\s+\S")
HASHTAG = re.compile(r"(?<![\w#])#(\w+)")
URL = re.compile(r"https?://\S+")
BAIT = re.compile(r"\b(comment|type|drop)\s+(?:a\s+)?['\"]?\w+['\"]?\s+(?:below\s+)?if\b|smash (?:that|the) like", re.I)


def seconds(stamp: str) -> int:
    total = 0
    for part in stamp.split(":"):
        total = total * 60 + int(part)
    return total


def chapters(description: str) -> list[int]:
    return [seconds(m.group(1)) for line in description.splitlines() if (m := STAMP.match(line))]


def check_chapters(desc: str, vid: str, report: Report) -> None:
    marks = chapters(desc)
    ok_start = bool(marks) and marks[0] == 0
    gaps = [b - a for a, b in zip(marks, marks[1:])]
    ok = ok_start and len(marks) >= 3 and all(g >= 10 for g in gaps)
    why = "none" if not marks else (
        "first is not 0:00" if not ok_start else
        f"{len(marks)} chapter(s)" if len(marks) < 3 else "a chapter is shorter than 10 s")
    report.add("video.chapters", vid, ok, ERROR, why,
               "list chapters in the description: first at 0:00, three or more, each 10 s or longer")


def check_lead(desc: str, vid: str, report: Report) -> None:
    # What shows before "...more": the opening paragraph, cut at LEAD characters.
    lead = desc[:LEAD].split(PARA_BREAK)[0]
    complete = re.search(r"[.!?](?:\s|$)", lead) is not None
    ok = complete and not URL.search(lead) and not lead.lstrip().startswith("#")
    report.add("video.description_lead", vid, ok, ERROR, repr(lead[:60]),
               f"make the first {LEAD} characters a complete sentence about the video, "
               "with no link or hashtag")


def check_video(video: dict, report: Report) -> None:
    vid = str(video.get("id") or video.get("title") or "?")
    title = video.get("title", "")
    report.add("video.title_length", vid, 0 < len(title) <= TITLE_MAX, ERROR,
               f"{len(title)} characters", f"keep the title at {TITLE_MAX} characters or fewer")
    key = (video.get("key_phrase") or "").lower()
    at = title.lower().find(key) if key else -1
    report.add("video.key_phrase", vid, 0 <= at <= KEY_PHRASE_WINDOW, ERROR,
               f"key phrase {'missing' if at < 0 else f'at character {at}'}",
               f"put the key phrase within the first {KEY_PHRASE_WINDOW} characters of the title")
    desc = video.get("description", "")
    check_lead(desc, vid, report)
    check_chapters(desc, vid, report)
    tags = video.get("hashtags") or HASHTAG.findall(desc)
    report.add("video.hashtags", vid, 3 <= len(tags) <= 5, ERROR, f"{len(tags)} hashtag(s)",
               "use three to five hashtags that describe the video")
    sources = [s for s in video.get("sources", []) if URL.match(str(s))]
    report.add("video.sources", vid, bool(sources) and all(s in desc for s in sources), ERROR,
               f"{len(sources)} source link(s)", "link every source in the description")
    pinned = (video.get("pinned_comment") or "").strip()
    report.add("video.pinned_question", vid, "what if" in pinned.lower() and pinned.endswith("?"),
               ERROR, repr(pinned[:60]), "write a pinned comment that asks a real 'what if' question")
    report.add("video.no_bait", vid, not BAIT.search(pinned + "\n" + desc), ERROR, "",
               "remove engagement bait; ask a question people want to answer")
    report.add("video.shorts_cut", vid, bool((video.get("shorts_cut") or "").strip()), WARN,
               "", "plan a Shorts cut that stands on its own")


def check_manifest(path: Path) -> Report:
    report = Report("video", str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    videos = data.get("videos", data if isinstance(data, list) else [])
    report.add("video.manifest", path.name, bool(videos), ERROR, f"{len(videos)} video(s)",
               'list videos under "videos"')
    for video in videos:
        check_video(video, report)
    return report
