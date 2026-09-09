# Private Artifact Filesystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one reusable private artifact filesystem primitive for byte-safe reads and immutable publication under a retained root authority.

**Architecture:** Keep Writing and source-context semantics outside this change. Add `harness.private_artifact_fs` as the public facade and OS-specific `private_artifact_fs_*` helpers that retain directory/file object identity through each operation.

**Tech Stack:** Python stdlib only, pytest, Windows ctypes for relative `NtCreateFile`, POSIX `dir_fd` operations with `O_NOFOLLOW`.

**Spec:** reusable private artifact custody primitive for retained root identity, bounded reads, and exact-byte immutable publication. This public plan is self-contained; private review receipts stay in scratch.

## Global Constraints

- Own only new `harness/private_artifact_fs*.py` modules and dedicated tests/docs.
- Do not edit Writing or source-context modules.
- No network, model calls, full Flywheel suite, commit, or push.
- Public source must stay clean and stdlib-only on the verifier boundary.
- New Python files must stay below the 300-line gate.
- Unsupported OS/backend combinations fail closed with typed errors.
- Root authority is a pinned opened object. A stable pathname is verified before
  each operation; if the pathname no longer resolves to the pinned object, the
  primitive fails closed. Path-only consumers need fd/handle handoff or a
  separately proven OS lock before claiming the same authority.
- Descendant directories are opened relative to the retained parent cap, then
  kept in the operation chain until the read or publication completes.
- Publication does not repair permissions after the final path exists. POSIX
  creates new files at mode `0600` and new directories at mode `0700`.
  Windows inherits the admitted root permissions and requires an admitted root ACL that
  already confines readers/writers appropriately. Windows write-capable roots
  deny delete sharing and allow write sharing for their own rename-based
  publication; read-only roots use `writable=False` to deny both write and delete.
- File flush errors fail the operation. POSIX directory metadata fsync is
  attempted and only documented platform "unsupported" errors are tolerated.
  Windows flushes the file handle before NT rename and makes no separate
  directory-metadata crash-durability claim.
- `ArtifactIdentity.to_json_dict()` and `from_json_dict()` provide the stable
  JSON shape: `platform`, `device`, and `inode`.

---

### Task 1: Public Contract

**Files:**
- Create: `harness/private_artifact_fs.py`
- Test: `tests/test_private_artifact_fs.py`

**Interfaces:**
- Produces: `PrivateArtifactError`, `ArtifactIdentity`, `root_identity`, `open_artifact_root`.
- `open_artifact_root(root, expected=identity, writable=False)` captures a
  read-only root authority. `write_new_or_same` on that authority raises `BUSY`.

- [ ] Write failing tests for the requested API and error code contract.
- [ ] Run `python -m pytest tests/test_private_artifact_fs.py -q` and observe import failure.
- [ ] Implement the public facade and backend dispatch.
- [ ] Run the focused test again.

### Task 2: POSIX Backend

**Files:**
- Create: `harness/private_artifact_fs_posix.py`
- Test: `tests/test_private_artifact_fs.py`

**Interfaces:**
- Consumes: public facade hooks.
- Produces: retained ancestor fd chain, bounded reads, safe parent creation, temp-link immutable publication.

- [ ] Write tests for symlink parent/leaf rejection, root drift, parent creation confinement, bounded reads, and idempotent/conflicting writes.
- [ ] Run focused tests to confirm failure.
- [ ] Implement POSIX relative fd operations with `O_NOFOLLOW`.
- [ ] Run focused tests on POSIX where available.

### Task 3: Windows Backend

**Files:**
- Create: `harness/private_artifact_fs_windows.py`
- Test: `tests/test_private_artifact_fs.py`

**Interfaces:**
- Consumes: public facade hooks.
- Produces: retained ancestor HANDLE chain, relative `NtCreateFile`, bounded reads, temp-rename immutable publication.

- [ ] Write tests using real Windows junction/symlink controls when available.
- [ ] Run focused tests to confirm failure.
- [ ] Implement Windows ctypes helpers using relative handles.
- [ ] Run focused tests on Windows.

### Task 4: Verification

**Files:**
- Test: `tests/test_private_artifact_fs.py`

**Interfaces:**
- Consumes: all previous task outputs.

- [ ] Run `python -m pytest tests/test_private_artifact_fs.py tests/test_file_backed_store.py tests/test_local_read_handle.py -q`.
- [ ] Run `python scripts/check_file_gate.py`.
- [ ] Run `python scripts/check_verifier_stdlib.py`.
- [ ] Run `python -m compileall harness/private_artifact_fs.py harness/private_artifact_fs_posix.py harness/private_artifact_fs_windows.py`.
- [ ] Run WSL focused tests if WSL is available.
