# Getting help with Flywheel

Start with `flywheel doctor`. It checks the interpreter, the installed version,
the Flywheel home, Git, which provider keys are set (by name only), whether a
local model server answers, and whether the relay coding agent is installed,
and it names the next step for anything that is not ready.

If that does not answer it, open an issue at
https://github.com/HarperZ9/flywheel/issues/new/choose and pick the template that
fits. A bug report asks for `flywheel doctor --json`, the command you ran, and
what you expected. Flywheel is maintained by one person, so the issue tracker is
the one support channel; there is no chat server and no paid support queue.

Security problems do not belong in a public issue. Open an issue titled
"Security contact request" with no details, and the maintainer will arrange a
private channel.
