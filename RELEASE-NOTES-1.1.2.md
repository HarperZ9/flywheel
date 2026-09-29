# Flywheel 1.1.2

This patch keeps private lanes out of public builds and corrects their local
source metadata. It includes the install and program-lookup fixes released in
the 1.1.1 engine, and the Telos 0.4.2 lane integration.

## What changed

- Private lane descriptions on registry, card and desktop surfaces use fixed
  neutral text. A CI gate checks those surfaces and the lane policy page.
- Source-only lane versions match their local source releases. A nested source
  project now resolves from its own project folder.
- Regression tests place source folders and stray descriptors on the host and
  check that private lanes remain unavailable in the frozen engine. Payload
  admission and the smoke plan also keep them out of the bundle.

## Changes carried from 1.1.1

- `flywheel install --help` prints help without installing. Invalid arguments
  fail before a package manager starts.
- Python lanes install through the interpreter that runs Flywheel, or their
  configured runtime. npm resolves through the shared guarded lookup on Windows.
- Program lookup excludes the current folder and unsafe PATH entries. Batch
  shims receive the guarded environment. A writable absolute PATH folder remains
  trusted; this does not secure a PATH controlled by someone else.
- Telos 0.4.2 joins the installer with its reviewed tool policy. Its native
  control tool remains excluded. Tools that start external programs require a
  separately approved T2 call.

## Limits

The 1.1.1 engine was published to PyPI before the private-description gate landed.
Upgrade to 1.1.2 to receive that containment change. The earlier tag is unchanged.
This release does not remove files from earlier downloads or repository history.

Private lane source code is not distributed in the wheel or installer. Correct
source metadata does not establish that a private workflow was exercised. The
regression tests use fixture folders and do not start those workflows.

The installed-engine checks do not drive the native interface. Consumer Windows
GUI operation, provider-backed workflows and macOS remain separate acceptance
limits. See the 1.1.0 notes for the earlier measured lane classes and their scope.

## Upgrade

Install the engine with `python -m pip install --upgrade flywheel-verify==1.1.2`.
For the Windows app, use the installer attached to this release and compare its
SHA-256 with the attached checksum file.
