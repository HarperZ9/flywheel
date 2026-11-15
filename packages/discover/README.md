# discover

discover tells you, before you release, what will stop people from finding your project, and how to fix each item. It checks a repository, a static site and a video plan against what search engines, AI search products, PyPI, npm, GitHub and YouTube read.

```bash
python -m pip install "git+https://github.com/HarperZ9/discover@v0.1.2"
discover repo . --gate
```

Python 3.11 or newer. Standard library only, no runtime dependencies.

```text
$ discover repo ../open-archives --github HarperZ9/open-archives
discover repo: ../open-archives
score 47/100  checks 12  failed 7  blocking 5

fixes:
  [error] citation.valid (1)
    CITATION.cff: missing
    fix: add CITATION.cff (cff-version 1.2.0, message, title, authors, version)
  [error] github.topics (1)
    HarperZ9/open-archives: 0 topic(s)
    fix: gh repo edit --add-topic <topic> (need 5+)
  [error] package.keywords (1)
    pyproject.toml: 0 keyword(s), need 3 or more
    fix: add [project].keywords with the words a person would search for
  ...
```

With `--gate`, the command exits 1 when a blocking check fails, so it can stop a release workflow. `--json` prints every finding. `--min-score N` also fails the gate under a score.

## What it checks

**`discover repo [PATH]`**

| Check | Blocks | Why it matters |
|---|---|---|
| README opens with a prose sentence within 30 lines | yes | GitHub, PyPI and npm show the opening first; AI search quotes it |
| A runnable command in a fenced block within 60 lines | yes | people decide in seconds whether they can try it |
| GitHub description (40 to 350 characters) and 5 or more topics | yes | repository search covers name, description and topics by default |
| Package keywords, classifiers, description, repository | yes | PyPI and npm search match these fields |
| CITATION.cff with the required CFF 1.2.0 keys, version matching the release | yes | GitHub shows "Cite this repository"; scholars and models cite the right version |
| The release's changelog section opens with a summary sentence before any list | yes | release notes are read by people deciding whether to upgrade |
| Homepage set, project URLs present | no | |

The release version comes from `--release`, or from the tag when run in GitHub Actions on a tag push.

**`discover site [ROOT]`** reads `discover.json` at the site root:

```json
{"origin": "https://example.github.io", "scope": "sitemap",
 "exclude": ["drafts/**"],
 "tools": [{"name": "Tool", "page": "tool.html", "version": "1.2.0",
            "registry": "pypi", "package": "tool-dist"}]}
```

Each indexable page needs a title, a meta description, a canonical URL on the origin, Open Graph title, description and image (the image file must exist), a Twitter card, and JSON-LD that parses. A page with `og:type` article needs an Article node. A tool page needs SoftwareApplication or SoftwareSourceCode, and its SoftwareApplication `softwareVersion` must equal the version in `discover.json`. A page with a playable video (`<video controls>` with a source) needs a VideoObject. Site-wide: sitemap.xml parses and every entry resolves to a file, robots.txt names the sitemap and does not block Googlebot, Bingbot, OAI-SearchBot, PerplexityBot or Claude-SearchBot, and llms.txt and llms-full.txt exist, name every tool, and give each tool's current version. `--online` compares those versions with PyPI, npm or GitHub Releases.

With `"scope": "sitemap"`, pages the sitemap lists must pass; other indexable pages are checked at warning level, and each one missing from the sitemap is listed.

**`discover video MANIFEST.json`** checks a video plan before upload: title of 70 characters or fewer with the key phrase in the first 40, a description whose opening paragraph is a complete sentence with no link or hashtag, chapters starting at 0:00 (three or more, each 10 seconds or longer, per YouTube's chapter rules), three to five hashtags, every source linked in the description, a pinned comment that asks a "what if" question, no engagement bait, and a planned Shorts cut. See `examples/video-manifest.json`.

## In GitHub Actions

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
- uses: HarperZ9/discover@v0.1.2
  with:
    mode: repo        # or site, or video
    path: .
```

Put it in the release workflow as a job the publish job `needs:`. In pull request CI, set `gate: "false"` to report without failing.

## What it does not do

It checks form. A sentence can pass the README check and still say nothing useful, and a correct JSON-LD node does not make a page rank. Every check here comes from a published platform rule or a field that a search system reads; see `docs/SOURCES.md`.

It does not, and will not, add keyword stuffing, hidden text, fake engagement or engagement bait. Search engines and YouTube penalise those, and they make a project harder to trust. The video check fails a pinned comment or description that asks people to comment a word or smash a button.

## Licence

AGPL-3.0-only. See [LICENSE](LICENSE). Cite with [CITATION.cff](CITATION.cff).
