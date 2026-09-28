<!-- Draft notes for the release after 1.1.0, reviewed before any tag. Nothing here is
measured by an installed-app check yet: the next windows-installed-acceptance.yml run on
the release commit must show telos at class A in both install modes before the telos
paragraph or a lane count ships. Merge with any other draft for the same release. -->

# Flywheel (next release)

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

- The classification comes from reading the 0.4.2 source and one instrumented call of
  each tool on Windows 11, on the bundled Node, with and without source folders beside
  the package. No call used the network or wrote outside the lane folder. It does not
  show what the programs `telos.room`, `telos.workflow` and `telos.proof` start would
  do, which is why those three need your approval.
- In the Windows app no source folder sits beside the bundled package and python is
  not on the lane's PATH, so an approved `telos.room` or `telos.workflow` call answers
  UNVERIFIABLE and names what is missing.
- The Node the installer bundles is the Windows x64 build. On Linux and macOS, Telos
  runs on the Node you install.
