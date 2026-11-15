# Research

Dated research notes sit in this folder as single Markdown files. Two folders are research
artifacts that were their own repositories. Each is the final tree of its source repository in one
commit that names the source commit, with its seal intact: the files its manifest lists are
byte-for-byte the published ones. Their checks run in `.github/workflows/research-artifacts.yml`
when a change touches one of them.

| Artifact | What it is | Check it | Came from | Checks |
|---|---|---|---|---|
| [witnessing-spine](witnessing-spine/) | Five adversarial steelmans of financial-sector technology claims and a synthesis, sealed by a manifest. | `python verify_manifest.py` | `HarperZ9/witnessing-spine` at `f6c29361` | manifest verifier, pytest, sealed bytes on Linux and Windows |
| [faithful-transpile](faithful-transpile/) | A working paper and experiments on faithfulness across minds: the thesis and companion papers, the `center/` code and the `sims/` experiments. | `sha256sum -c MANIFEST.sha256` | `HarperZ9/faithful-transpile` at `65ebae20` | pytest on `center/tests`, manifest, sealed bytes on Linux and Windows |

Both have a Zenodo deposit, and the move changes nothing in either:

- The Witnessing Spine: [doi.org/10.5281/zenodo.20778927](https://doi.org/10.5281/zenodo.20778927),
  cited in the `witnessing-spine` README.
- The Conservation of Faithfulness: [doi.org/10.5281/zenodo.23126484](https://doi.org/10.5281/zenodo.23126484),
  cited in the `faithful-transpile` README. The deposit holds the paper as PDF, HTML and Markdown.
