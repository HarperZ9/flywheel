<!-- Draft notes for the release after 1.1.0, reviewed before any tag. Nothing here is
measured by an installed-app check yet: the next windows-installed-acceptance.yml run on
the release commit must show telos at class A in both install modes before the telos
paragraph or a lane count ships. Merge with any other draft for the same release. -->

# Flywheel 1.1.1

A patch release for two install defects and one class of lookup defect. `flywheel install`
now installs only what its arguments name, pip lanes install into the Python that runs
Flywheel, npm lanes install on Windows, and every program the engine starts by name is
found only in an absolute PATH folder, never in the folder you run it from. It also adds Telos 0.4.2 as a lane in the Windows app.

## Who was exposed

- **Anyone who ran `flywheel install` with an argument it did not know.** Every release
  from 0.3.0 through 1.1.0 skipped unknown arguments, so `flywheel install --help`,
  `flywheel install gather`, `flywheel install --lanes=gather` and
  `flywheel install --lanes` with no value each installed every pip and npm lane.
- **Anyone who installed a pip lane.** `flywheel install` and the app's install action
  ran `pip` by name, so the lane went into whichever Python owned the first `pip` on
  PATH. When that was not the Python running Flywheel, the lane installed and then did
  not import. On Windows a `pip.exe` in the current folder ran first.
- **Windows users installing learn.** npm on Windows is `npm.cmd`, and starting it by
  the bare name `npm` fails, so `flywheel install --lanes learn` always failed there.
- **Windows users who run Flywheel from a folder holding files they did not write**, such
  as a cloned repository, a download folder or a task folder of model-written code.
  Windows starts a bare program name from the current folder before PATH, and so do
  `shutil.which` and `cmd.exe`. The engine started git, lean, node, npm, ssh-keygen,
  the Claude, Codex and OpenCode command-line tools, lane commands, MCP, LSP, DAP and
  ACP servers and configured hook and gate commands by bare name. The oracle's shell
  looked up `python` and `pytest` in the task folder first, next to the candidate's
  files, so a planted `python.cmd` there could print a passing result. On macOS and
  Linux the same happened only through a relative or empty PATH entry such as `.`.

The planted-program cases were reproduced against 1.1.0 in the tests that ship with this
release: each plant ran, or was reported as the installed tool. We have no report of
this being used against anyone; that is an absence of reports, not evidence it did not
happen.

## What changed

- `flywheel install` parses its arguments strictly. `-h` and `--help` print the usage
  and exit 0. An unknown argument, a flag without its value, a flag given twice, an
  unknown profile or an empty lane list prints the error and the usage and exits 2.
  Nothing installs unless every argument parses. Flags take `--lanes gather` or
  `--lanes=gather`.
- pip lanes install with `<python> -m pip`, where `<python>` is the interpreter running
  Flywheel, or the lane's pinned `runtime_python` when you set one. The installed
  Windows app has no Python of its own; its bundled lanes need no install, and a pip
  lane there needs a pinned `runtime_python` or the install stops with
  `pip_interpreter_unavailable`.
- npm lanes resolve `npm` safely, `npm.cmd` on Windows. With no safe npm the install
  stops with `npm_unavailable` and a message naming what to install.
- The package manager runs in a new empty folder, so a `pip` package or an `.npmrc` in
  your current folder is not read.
- Every program the engine starts by name resolves through one shared lookup: only
  absolute PATH entries, none that reaches the current folder or the folder the program
  will run in, directly or through a link or junction, and no drive-relative name such
  as `C:tool`. A shell the engine starts gets the same PATH, and on Windows it is told
  not to search its own folder first. So does a batch file the engine starts on
  Windows, such as the shim npm installs for a tool, because `cmd.exe` runs it and
  would otherwise find the `node` it names in the folder it runs in. Windows system tools (taskkill, icacls, wevtutil,
  wsl, Windows PowerShell) come from the System32 folder.

## What you may notice

- A tool reachable only through a relative PATH entry, or only from the current folder,
  is now reported as not installed. Put it in an absolute PATH folder, or name it by
  full path where Flywheel takes one.
- A relative program path in a configuration, such as `./tool` for a command-line
  endpoint, is refused. Use a full path.
- On Windows a program that is a batch file (`.cmd` or `.bat`), such as the shim npm
  installs for a command-line tool, is refused when an argument holds a character
  `cmd.exe` would run as a command: `"`, `%`, `^`, `&`, `|`, `<`, `>` or `!`. Most
  prompts hold one of them. Where the tool ships a native `.exe`, Flywheel prefers it.

## Lane updates

- **Telos joins the Windows app.** Telos 0.4.2 (`project-telos-mcp` on npm) runs as a
  lane on the Node the installer bundles. Its card reads the workstation catalog and
  assembles proof packets that recompute their own verdict. 37 of its 41 tools run on
  an ordinary lane call. `telos.room`, `telos.workflow` and `telos.proof` start
  programs from outside the package: python from your PATH, source folders beside the
  package, a witness script. Each of those runs only on a call you approve at T2.
  `telos.native.control`, the package's browser and desktop driver, is not in the
  build. `flywheel install telos` installs `project-telos-mcp@0.4.2`, which needs Node
  20 or later.
- **Why Telos was out of 1.1.0.** Its 0.4.1 package carried CAPTCHA solving and
  browser fingerprint spoofing code. 0.4.2 removes that code, and the lane no longer
  passes the variable that located it. Each tool was then classified again from the
  0.4.2 code. The table is in `docs/features/lane-tool-policy.md`; the measurement
  behind it is in `project-docs/lanes/evidence/telos-0.4.2-tool-measurement.json`.

## Limits

- A folder on your PATH that someone else can write is still trusted. This release
  closes the current-folder route, not a PATH you do not control.
- git reads a repository's own configuration. Some git calls here already turn off
  hooks and the file-system monitor; the others do not, and this release does not
  change that.
- `flywheel auth` opens your browser through Python's `webbrowser` module, which does
  its own lookup on Linux and is not routed through the shared lookup.
- Checked with the whole test suite on Windows 11 and on Ubuntu 24.04 as a non-root
  user with the system Python. macOS was not run for this release.

### Telos lane

- The classification comes from reading the 0.4.2 source and one instrumented call of
  each tool on Windows 11, on the bundled Node, with and without source folders beside
  the package. No call used the network or wrote outside the lane folder. It does not
  show what the programs `telos.room`, `telos.workflow` and `telos.proof` start would
  do, which is why those three need your approval.
- In the Windows app no source folder sits beside the bundled package, so an approved
  `telos.room` or `telos.workflow` call answers UNVERIFIABLE and names what is missing.
  It still starts `python --version` from your PATH when python is on it.
- The engine passes no telos tool an argument: the lane call and Plugins drop what a
  caller sends, and the approval sheet lists it as dropped. An agent run passes the
  model's arguments through, so it cannot select a telos tool.
- The Node the installer bundles is the Windows x64 build. On Linux and macOS, Telos
  runs on the Node you install.
