# The Flywheel test suite

This directory holds 11,212 tests across 969 files. The suite is the evidence
that the engine does what its docstrings claim, and a good change arrives with
a test that fails without it. This file is a map of how the tests are laid out
and how to run them, plus the four gates that tend to surprise a newcomer.

## Layout

Test files sit flat in `tests/`, one per source area, named `test_<feature>.py`
after the module or behavior they cover. `test_oracle.py` covers `oracle.py`,
`test_lanes.py` covers the lane layer, and so on. Inside a file, each test
function is named for the thing that would break in the world, so a red name
tells you which real behavior broke.

Not every file here collects tests. Support modules that end in `_fixtures.py`,
`_fixture.py`, `_helpers.py`, or `_probe.py` hold fixtures and fakes for the
real tests to use, and `conftest.py` wires the shared ones. The `fixtures/` and
`enterprise_envs/` directories hold data and scenario inputs. One test runs
outside pytest: `telos_browser_bridge.test.mjs` is a Node test for the browser
bridge.

## Running a slice against the full suite

Run the slice that covers what you changed. `CONTRIBUTING.md` sets this as the
default, because the full collection takes long enough that nobody runs it while
iterating.

```bash
python -m pytest tests/test_<the_feature_you_touched>.py -q
```

The full suite is 11,212 tests across 969 files. Continuous integration shards
it four ways and runs all of it. A per-test timeout of 60 seconds is configured
in `pyproject.toml`, so a single wedged test cannot hang the run. `CONTRIBUTING.md`
lists the packages a full local run needs.

## Gates that surprise people

These run on every pull request, each one is runnable locally, and each has a
test in this directory that pins its behavior. A red here usually points at a
rule that is not obvious from the code you touched. `CONTRIBUTING.md` carries
the full list with the command for each.

### The 300-line file gate

`python scripts/check_file_gate.py`, pinned by `tests/test_file_gate.py`.

No source file under `harness/`, `scripts/`, or `tests/` runs past 300 lines.
Files that already exceeded the limit are frozen on a burn-down list with their
current counts, and the list can only shrink. A new file over the limit fails,
and a grandfathered file that grows fails. The point is legibility: a file you
can read in one sitting is one a new lead can take over.

### The tracked-path length gate

`python scripts/check_path_length.py`, pinned by
`tests/test_check_path_length.py`.

No path that git tracks runs past 180 characters, and nothing is
grandfathered. Windows refuses a full path over 259 characters unless
core.longpaths is set, and a first clone runs with the default, so every
character in a tracked path is one fewer for the directory someone clones into.
The gate came from a benchmark run that wrote its output under a path that
repeated its own root, which left 206-character paths in the tree.

### The stdlib accept path

`python scripts/check_verifier_stdlib.py`, pinned by
`tests/test_accept_path_purity.py`.

The offline verifier has to run on a bare interpreter with no pip install, no
network, and no GPU, because that is what a stranger runs to re-derive a result.
The check walks the import closure of the verifier entry points and asserts that
nothing reachable imports a third-party package. The test goes further and
asserts that no learned model runtime is reachable from that path, which is the
C2 invariant from `oracle.py`: the oracle is the only thing that accepts.

### The disproof gate

`python -m harness.cli_entry gate`, pinned by `tests/test_gate_end_to_end.py`.

One command runs the whole chain end to end on a bare interpreter: an exact
symbolic oracle disposes candidates, the group is scored, the winner is sealed
into an envelope, and the envelope is re-witnessed. If the run cannot reach
MATCH, the premise that these parts compose is false, and the gate says so for
the price of one run.

### The writing gate

`python scripts/check_writing.py --gate README.md`, pinned by
`tests/test_check_writing.py`.

Hard prose rules apply to the calibrated public files, and one of them bans em
dashes. This keeps published surfaces in the house register and stops a stray
device from shipping. The gate runs only on the files it is pointed at, so a
comment or a private note is not held to it.
