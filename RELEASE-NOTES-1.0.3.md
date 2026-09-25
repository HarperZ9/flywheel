# Flywheel 1.0.3

A self-hostable, model-agnostic AI workstation and coding harness. Flywheel runs a task
with any model, frontier or local, behind one OpenAI-compatible surface, and your keys and
data stay on your machine. An answer is accepted only when a real check passes, such as a
test run or a Lean proof. Each accepted answer carries a sealed receipt, and the witness
re-runs that receipt offline to return MATCH, DRIFT, or UNVERIFIABLE.

1.0.3 is mainly a fix release. Its largest group of fixes closes several ways the verifier
could accept a candidate that had not earned the pass. Two known Lean routes stay open,
and the Limits section names them. 1.0.3 also fixes a Windows lock race and
brings the three version declarations into agreement. A mismatch between them stopped
the 1.0.2 installer build.

## What 1.0.3 fixes

- Windows lock race (#292). On Windows, two callers that found the same lock file empty
  could both try to write its first byte. The later write could fail with
  PermissionError, and that caller then never waited for the lock, so a duplicate native
  continuation start could fail with STORE_COMMIT_FAILED (HTTP 500). That refused write
  now counts as contention when another caller holds the lock, and it still raises when
  the lock is free. The lock file is opened unbuffered, and setup time now counts
  against the acquisition deadline. Grants, journeys, index jobs, browser admission, and
  bulletin identity share this lock implementation. POSIX behavior is unchanged.
- Skipped tests no longer pass (#289). The pytest oracle treated a skipped test as
  neutral, so one passing test beside skips graded PASS. A candidate that answered one
  input and skipped every other case passed accept_gate with the held-out tier on, and
  RL collection paid it reward 1.0. Any skipped or xfailed test in the run's report now
  grades FAIL, and the oracle output says why. A task that must not run a test excludes
  it in the recorded command with --deselect, and the witness re-runs the same
  exclusion. A PASS envelope that an earlier version sealed over a run with a skip now
  re-witnesses DRIFT.
- The task workdir is restored after every run (#289). Every pytest oracle run and every
  witness re-run now restores the task workdir from a snapshot taken once the candidate
  is written. The restore removes added entries and writes changed or removed files back
  byte for byte. Before, a candidate that wrote a conftest.py or rewrote the task's test
  file could change how the next candidate in the same workdir was graded. A task link
  that the run changed is not recreated (see Limits).
- Each pytest run grades its own report (#288). Every run used to write its JUnit report
  to the same file, and nothing removed the old one. A candidate that called os._exit(0)
  before pytest wrote the report was graded on the previous run's report, so it could
  pass with no function at all. Each run now writes a report under its own name, and an
  exit 0 with no fresh report is FAIL. A failing outcome in the run's own report
  outranks a forced exit code, such as one set with atexit.register(os._exit, 0). The
  witness checks the sealed verdict as well as the hash, and an envelope sealed on a
  stale report re-witnesses DRIFT.
- Lean candidates are replayed through leanchecker (#287). A file could prove False by
  adding an unchecked declaration through a metaprogram that set debug.skipKernelTC.
  lean exited 0 and #print axioms reported no axioms. A Lean candidate that passes the
  kernel run and the axiom audit is now compiled and replayed with leanchecker from the
  same toolchain. A compile or replay that refuses the candidate is FAIL. A replay that
  judges nothing is UNVERIFIABLE with a named reason. That covers a step that cannot
  start, such as a toolchain with no leanchecker, an imported module that leanchecker
  cannot load, and an earlier LEAN_PATH entry that holds a module named like the
  candidate's. The receipt gains a validation_level field. The replay adds about 3.0 to
  4.4 seconds per candidate that reaches it (n=3). Two other routes still pass after the
  replay (see Limits).
- The --boot flag no longer raises NameError (#290). run_loop raised NameError whenever
  a caller passed boot_root without a boot packet, which broke
  python -m harness.cli TASK --boot ROOT. It now builds the packet.
- Installer upgrades over a stray dist-info folder (#278). The installer's metadata
  cleanup aborted with MISSING_METADATA_BINDING when an earlier install had left an
  unrelated .dist-info folder with no METADATA file. The cleanup script now skips that
  folder and still refuses a malformed flywheel-verify folder. This fix merged before
  1.0.2. 1.0.2 built no installer, so the 1.0.3 installer is the first built with it.
  No installed run has tested the fix yet.

## Other changes

- Lane versions match the package index (#283). Five lanes that were disabled for pip
  installs now point at their published distributions: relay (flywheel-relay 0.2.5),
  mneme (flywheel-mneme 0.4.2), plexus (plexus-mesh 0.2.2), canon (flywheel-canon
  0.2.0), and accountable-surface (0.3.1, launched through accountable-surface-mcp).
  articulate moves to articulate-writing 0.4.0 and its stdlib-only articulate-mcp
  server, and chorus moves to 0.3.1. gather 1.8.2, index 2.13.0, forum 1.14.0, and
  calibrate-pro 2.0.0 now declare the versions the index carries, so a current install
  no longer reports installed_version_mismatch. telos stays disabled because it has no
  published npm distribution.
- The writing linter gains five report-only detectors for higher-order structure (#275):
  parallel_enumeration, aphoristic_landing, repeated_syntactic_frame, specificity_floor,
  and rhythm_variance. corrective_negation, report-only since 1.0.2, now works at clause
  level and across adjacent sentences. These categories report counts and spans and
  never fail --gate. Gated totals were unchanged across 70 fixture and profile
  combinations.
- Shorter tracked paths for Windows clones (#286). Before, a Windows clone without
  core.longpaths failed once the clone directory reached 52 characters. Benchmark output
  that sat under a doubled run path now sits at its intended paths, and the spin
  benchmark writer resolves its output root first. The longest tracked path fell from
  206 to 130 characters, and a new CI gate fails on any tracked path over 180
  characters.
- Oracle reports are untracked (#291). The repository no longer tracks 1,149 pytest
  oracle reports, 63 of which held absolute local paths. A new CI job fails on a tracked
  JUnit report that names a host or an absolute path.
- One version across all declarations (#281). pyproject.toml, desktop/pubspec.yaml, and
  desktop/lib/version.dart all say 1.0.3. The same change fixes a Windows CI race in a
  process-kill test by writing the child pid through a temporary file and os.replace.

1.0.2 reached PyPI only. Its release change (#279) left desktop/lib/version.dart at 1.0.1,
and the installer build stopped at the version check before packaging. 1.0.3 includes
everything in 1.0.2.

## Upgrade

- Engine: pip install -U flywheel-verify
- Desktop app: the Windows installer (Flywheel-Setup-1.0.3-x64.exe) is attached below.

## Limits

- Code running inside the pytest process can still forge its own report or keep tests
  out of it. A task whose tests skip on one platform now fails every candidate there;
  no shipped task uses a skip API.
- The workdir restore does not undo writes outside the workdir or writes from a process
  the candidate leaves running. When the run changed or removed a task link, the restore
  leaves that link as it is and raises WorkdirRestoreError. A run that changes a task
  file also changes its own grade, because the restore protects only the runs after it.
- The math oracle does not check which theorem a candidate proves. LeanOracle.verify
  never reads its task argument, so any closed theorem passes. In one test,
  theorem unrelated : True := trivial passed at validation_level leanchecker_replay
  against a task that asks for a Python function. A fix that binds each proof to a
  pinned statement is proposed and not built.
- A def whose value uses an axiom that a metaprogram added can prove False and still
  pass. The observed receipt shows validation_level exit_code and an empty
  axiom_footprint, because the footprint audit reads only theorem and lemma
  declarations named in the source.
- The default --boot-budget of 1500 was too small for the Flywheel repository itself.
  In one run on its 5,505 files, the boot stage took 154 s and returned DRIFT with
  budget_exceeded, so the prompt was not hydrated.
- No installed run has tested the #278 cleanup fix. Its regression tests run only with
  a signed Inno Setup compiler (FLYWHEEL_ISCC), which no CI workflow sets.
  windows-installed-acceptance last ran on 2026-09-19, before #278 merged.
- The installer bundles lane sources pinned before #283, so its relay, mneme, plexus,
  canon, chorus, and accountable-surface lanes are older than the versions pip installs.
- On the shipped benchmark the verified loop shows no measured accuracy uplift over
  single-shot. The interval includes zero.
- A receipt proves a check reproduces. It does not prove the answer is true of the world.
