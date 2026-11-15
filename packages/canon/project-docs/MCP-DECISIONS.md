# MCP-DECISIONS — the door

The bands before this one all faced inward. Everything that read a canon record
lived inside this repository, so a harness holding the files canon writes had no
way to ask canon what it believes. This band is the door: an authored-block
loader, a stdio MCP server over it, and a console script that reaches both.

Decisions continue the repository numbering; V4 ended at D-67.

## D-68 The door reads. It never writes.

Six tools ship: `canon.status`, `canon.doctor`, `canon.blocks`, `canon.render`,
`canon.validate`, `canon.check`. Every one of them reads. No surface is spliced,
no vault is mirrored, no gate is raised.

Reconcile is the band that decides whether a drift is a mechanical fast-forward
or a conflict a human must adjudicate, and it writes instruction files and raises
durable gates. That is an action with a human behind it, and an action does not
belong on a door any caller can knock on. It stays a library call a caller wires
deliberately.

The claim is a control, not a comment. `test_no_tool_on_this_server_writes_anything`
digests a tree holding a real managed surface, calls every tool against it, and
digests it again. A tool that grew a write changes a hash there.

## D-69 The tool names are the probe vocabulary, not a house style.

A lane probe calls `<name>.status` or `<name>.doctor` and reads the lane as live
only when one of them answers. Naming these tools anything else would leave the
lane permanently unprobed while every call still worked by hand, which is the
failure that looks like success. `test_the_tool_list_carries_the_names_a_lane_probe_looks_for`
pins the list.

## D-70 status is liveness. doctor is readiness. doctor can be false.

`canon.status` answers whether the server is alive. It reads nothing and stays
true whatever the block directory holds, because a probe asking whether the
server answers must not get a false from configuration.

`canon.doctor` answers whether the server is ready, and reads false when the
block directory is missing or holds a file that will not load. That is the way
this answer can be wrong. A doctor that returns true in every reachable state
reports its own existence, not the health of anything.

## D-71 The drift roots come from the environment, never from a tool argument.

`canon.check` runs the drift leg, which reads the managed surfaces on disk. The
roots come from `CANON_HOME` and `CANON_WORKSPACE`, so the location is operator
configuration.

Taking them as tool arguments would have been shorter and would have turned an
MCP tool into a general file-read surface with a schema on top: a caller passes a
root, canon resolves the catalog under it, and the contents come back in the
answer. The path set stays fixed and operator-owned instead.

## D-72 The check folds the block load, so a vacuous pass is a failure.

`canon_check` reports None for a leg whose seam is not wired and folds only the
legs that ran, which is the right treatment for a leg. The pool is not a leg. It
is the subject every leg voted over, so a pool that is not the authored set makes
a pass a statement about something else.

`canon.check` folds the load into `ok`. A directory holding a file that will not
load yields a smaller pool and reads false. No directory at all is the same
failure at its limit, every leg voting over the empty set, and it reads false
too. `pool_available` and `pool_complete` tell the two apart, `reasons` names
which happened, and `does_not_prove` says in the payload that an unwired leg
checked nothing.

## D-73 A block file that does not load is reported, never skipped.

`load_blocks` returns the records that loaded and one problem string per file
that did not, and the count of the two together is the count of files it saw. A
loader that skipped a malformed file would produce a pool that looks exactly like
a clean one while missing the record someone just wrote. The drop is worse than
the refusal because the drop is silent.

Only `*.json` is read. The block directory ships prose beside the records, and a
loader that globbed everything would report the prose as a malformed record on
every call.

## D-74 Three verbs on the console script, all read-only.

`canon mcp` runs the server, `canon check` prints the aggregate check and exits
non-zero when a wired leg or the pool fails, `canon blocks` lists the authored
set. The check verb and the check tool call the same function, so a build gate
and a harness question cannot disagree about what canon believes.

`[project.scripts] canon = "canon.cli:main"` declares the entry point. The
version stays at 0.0.0: publishing is a separate decision. The server serves that
same number, and a test holds the two equal. A harness reads it from serverInfo
and a lane roster reads it from install metadata, so a second hand-typed number
here would show up over there as a stale install rather than as the typo it is.

Later: 0.2.0 published the package to PyPI, so the number now follows each
release. `src/canon/_version.py` holds it for the package, `canon --version`
and both MCP servers, and a test holds it equal to pyproject.toml.

## D-75 The block directory is resolved, and this repository ships none (honest null).

`CANON_BLOCKS_DIR` wins when set; otherwise the loader looks for a `blocks/`
directory beside the package and reports None when there is none. There is no
`blocks/` directory on this branch, so a fresh clone answers `canon.doctor` with
`ok: false` and `canon check` exits 1. Both answers are true: no authored set is
configured, and nothing was checked. The alternative was a default that invents a
path, which would report a clean load of an empty directory that does not exist.
