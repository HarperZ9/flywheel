# Changelog

## Unreleased

- Add the Claude plugin directory listing fields: display name, keywords,
  homepage, documentation, support, privacy and terms links, and a 1024 px icon.
- Add PRIVACY.md and a data and privacy table to the README. The plugin and its
  ZIP now carry both files.

## 0.2.0 - prepared for release

- Add a portable root plugin manifest while preserving Codex and Claude
  compatibility metadata and the existing skill directory layout.
- Include the skill and plugin ZIPs with the Flywheel product release candidate.
  Accepted checksums bind the reviewed archive bytes before asset publication.
- Document the full native client and the separate evidence-task skill package.
  This skill package includes no model or MCP server and grants no permissions.

Directory approval and live client installation remain separate acceptance work.

## 0.1.0 - 2026-09-07

- Added a portable evidence workflow with explicit sources, measurements, unknowns, and false-success controls.
- Discover optional MCP tools at runtime instead of relying on host-specific identifiers.
- Added examples for public lane-count checks, Bulletin feedback checks, and negative readiness shortcuts.
- Added a constraints reference covering public-source boundaries, MCP primitives, measurement controls, and readiness limits.
- Added Codex and Claude plugin manifests and repository marketplace entries.
- Added reproducible standalone skill and plugin downloads with checksums.
- Exposed the skill and constraints as public MCP resources in source-built engine packages, with a source/package drift check.
