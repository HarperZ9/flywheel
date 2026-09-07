# Flywheel 0.4.1

Hook approval now binds the exact sealed registrations selected for a run.
If the registry changes after approval, the gateway refuses the run before
constructing a runner. Registration itself never executes a hook.

## Hook compatibility

Hook registration and execution use private gateway routes and operation
grants. Reading the hook registry also requires gateway authentication.
Clients preparing a `hook.run` operation supply the event, context, and exact
selected sealed `registrations`. The proposal shows the selected commands.
After a registry conflict, read the registry again and prepare a new operation;
do not reuse an approval for different commands.

All supplied registrations are checked before execution, including direct
library calls. Registry seals, shell executable basenames, and subprocess
timeouts are checked on the corresponding paths. These controls bind approved
commands; they do not establish that an approved command is harmless.

See [the hook API guide](WRAPPER-HOOKS.md) for the operation contract.

## Evidence skill resources

The engine includes versioned, hash-bound MCP resources for Flywheel Evidence
Task 0.1.0. Resource reads use a fixed allowlist and the packaged wheel includes
the resource data. The standalone skill and Codex/Claude Code plugin remain
available as separate downloads from the
[skill release](https://github.com/HarperZ9/flywheel/releases/tag/skill-flywheel-evidence-task-v0.1.0).

The skill helps structure source checks and report omissions. Its instructions
do not independently verify arbitrary claims. Package validation does not
establish installation in every host or approval by an external marketplace.

The engine and desktop declare the same 0.4.1 version. Release artifacts and
checksums identify the exact build; build and publication status are reported
by the corresponding release workflows.
