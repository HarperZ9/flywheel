# Changelog

## 0.1.2 (2026-10-23)

The GitHub Action now pins actions/setup-python to a full commit SHA, so repositories that require SHA-pinned actions can use discover without an exception.

## 0.1.1 (2026-10-23)

With no release version named, the release-notes check now reads the newest released changelog section instead of an Unreleased placeholder, so pull request reports describe what shipped last.

## 0.1.0 (2026-10-23)

discover tells you, before a release, what will stop people from finding your project and how to fix each item. It checks a repository, a static site and a video plan, scores the result, and with `--gate` fails CI when a blocking item is missing.

- `discover repo`: README opening and run command, GitHub description, topics and homepage, package keywords, classifiers and URLs (pyproject.toml, package.json, Cargo.toml), CITATION.cff, and a benefit-first summary for the release being cut.
- `discover site`: title, description, canonical URL, Open Graph and Twitter card with an image that exists, JSON-LD that parses and carries Article, SoftwareApplication or VideoObject where the page needs one, sitemap.xml, robots.txt access for search crawlers, and llms.txt and llms-full.txt naming every tool at its current version. `--online` compares versions with PyPI, npm and GitHub Releases.
- `discover video`: title length and key phrase position, a description opening that stands on its own, chapters from 0:00, three to five hashtags, linked sources, a pinned "what if" question, no engagement bait, and a planned Shorts cut.
- A composite GitHub Action, `HarperZ9/discover@v0.1.0`.
