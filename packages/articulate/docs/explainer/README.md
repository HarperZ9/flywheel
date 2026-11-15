# Articulate explainer

`index.html` is a single self-contained page that explains how Articulate
checks a draft, gates it by profile, scores its texture and replays a receipt.
It is published at <https://harperz9.github.io/repo-explainers/articulate.html>.

Open `index.html` in a browser to read it from a checkout. It loads two
typefaces from harperz9.github.io and falls back to system fonts offline.

The findings, offsets, scores and verify outcomes on the page come from running
this repository at commit c94bf17 on the sample draft the page shows. The same
output came from `articulate-writing` 0.9.0 installed from PyPI. When the
detector or the receipt format changes, rerun the commands in the page's "Try
it" section and update the values in the same pull request.
