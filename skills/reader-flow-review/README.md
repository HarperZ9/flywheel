# Reader Flow Review

Version: 0.1.0. Experimental standalone skill release.

Reader Flow Review is a portable Agent Skills folder for scoped prose review. It helps an agent critique or revise a specific passage without flattening working voice, over-polishing fiction, or turning source material into unsupported certainty.

## Install

Copy the `reader-flow-review` folder into the skill directory documented by your agent runtime. Keep `SKILL.md`, this README, `SOURCE-ATTRIBUTION.md`, and `EVALUATION.md` together if your host supports bundled skill documentation.

This release does not install itself, enable itself automatically, add an MCP server, or grant publishing authority. A successful archive build only proves the source package was assembled reproducibly; host installation and live behavior remain separate checks.

## Use

Ask explicitly for a reader-flow review or scoped revision of a specific prose passage. Good trigger examples:

- Use `reader-flow-review` to identify the dominant reader-flow issue in this paragraph.
- Revise this passage for clarity while preserving its voice.
- Give me two audience-specific versions of this excerpt.

The skill is intentionally narrow. It is not a full writing assistant, source verifier, publication approver, or global style policy.

## Build the release archive

From the repository checkout:

```text
python scripts/build_reader_flow_skill_bundle.py --out build/skill-downloads
```

The builder creates a deterministic standalone ZIP, `manifest.json`, and `SHA256SUMS`. The archive contains only allowlisted public files and the repository license.

## Tag plan

Use a skill-prefixed tag such as `skill-reader-flow-review-v0.1.0` if this standalone skill is released. Do not use a platform `v*` tag for this skill-only artifact.
