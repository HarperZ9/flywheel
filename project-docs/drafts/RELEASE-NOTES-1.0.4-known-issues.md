<!--
Draft of the 1.0.4 known-issues correction for the release owner to review and publish.
Evidence: the 1.0.4 engine rebuilt from tag v1.0.4 with the release workflow's freeze
steps, run with a System32-only PATH and a throwaway profile, plus the 1.0.4 release's
own smoke receipt. The released installer binary was not re-measured; PyInstaller output
is not byte-reproducible, so the rebuild's digest differs from the release's. Remove this
comment before publishing.
-->

# Flywheel 1.0.4: known issues in the Windows app's lanes

The 1.0.4 notes describe the Windows installer's lanes more strongly than the
installed app delivered. We rebuilt the 1.0.4 engine from its release tag with the
release's own freeze steps and ran it the way a fresh machine would: no Python, no
Node and no lane packages on the PATH, and a throwaway profile. This page corrects
five statements. The engine you get from `pip install flywheel-verify` is not
affected; every item below is about the installed Windows app.

## What the notes said, and what we measured

**"1.0.4 brings the Windows installer level with a pip install."** It did not
for lanes. In the installed app one lane, bulletin, ran its main read actions.
Nine bundled lanes (gather, crucible, chorus, index, plexus, mneme, canon, relay and
accountable-surface) answered only their status and doctor tools and refused every
other tool with `CAPABILITY_NOT_ADMITTED`. forum, local-model and writing did not
start. articulate, calibrate-pro, learn and telos were not in the installer. The
same machine ran read calls on 13 lanes from a pip install and on 16 from a source
checkout.

**"The installer bundles the current lanes," including forum 1.14.0.** forum 1.14.0
is in the installer, but the bundled forum process exits as it starts, because the
build left out the data file that holds its default roster. The 1.0.4 release check
counted that exit as a pass. Its receipt records forum's exit code as 1 next to an
overall result of PASS.

**"A lane now starts with a base set ... and any variable you grant it by name with
`env_allow` in `lanes.json`."** This holds for lanes that run from pip or npm. The
ten lanes bundled inside the Windows app start with a fixed set of eleven system
variables instead. A variable you grant with `env_allow` does not reach them, and
neither do `FLYWHEEL_HOME` or a lane's own declared settings. A key saved in the
app's Keys panel reaches no lane. The Upgrade step that says to add
`"env_allow": ["ANTHROPIC_API_KEY"]` to the forum or accountable-surface row has no
effect in the app.

**"When the gateway launches the bundled local-model lane, it confines the agent to
its own `--root`."** The confinement itself is in 1.0.4, but the installed app never
used it. The app started the local-model lane as `python -m harness.local_mcp` and
the writing lane as `python -m harness.writing_mcp`, found through your PATH. On a
machine with no Python, neither lane starts. On a machine whose `python` has an
older flywheel-verify, the app runs that older local agent, which predates the 1.0.4
grant fix. The last point is inferred from version order; we measured the launch
command and saw the app pick up a 0.3.5 install, but did not run that agent against
the grant cases.

**README: "About fifteen composable lanes ship in the roster, ten of them bundled
natively from source."** Ten lanes are bundled from source. In the 1.0.4 app, nine
of them answer a health check only and the tenth, forum, does not start, so the
sentence reads as more than the app delivers.

## If you run 1.0.4 today

- For lane work, use the engine from pip: `python -m pip install -U flywheel-verify`,
  then `flywheel lanes --probe` to see which lanes answer. Lane keys granted with
  `env_allow` work there.
- In the Windows app, read a lane's "live" status as "the lane answers its health
  check", not as "its main action runs".
- If Python is on your PATH and you use the app's local-model or writing lane, make
  sure that Python has flywheel-verify 1.0.4, because the app runs that copy:
  `python -m pip install -U flywheel-verify`.

## What changes next

The next release rebuilds how the app runs lanes: each lane's main tools are admitted
under a reviewed policy, local-model and writing run inside the bundled engine, forum
ships its data files, articulate, calibrate-pro and learn join the installer with a
bundled Node runtime, and each lane card states its setup. Its notes list what an
installed-app check measured for every lane, including the lanes still below that bar.
