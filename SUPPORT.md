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

If a command crashes, Flywheel writes a crash report to `crashes/` in the
Flywheel home and prints its path. The report holds the version, OS, Python,
the command name and the traceback, with your home folder replaced by `~` and
any environment value whose name says key, token, secret or password replaced
by that name. Nothing is sent; read the file, then attach it to an issue if you
want to. Set `FLYWHEEL_DEBUG=1` to see the raw traceback instead.

`flywheel update` checks PyPI for a newer release (one request, only when you
run it) and prints the upgrade step for the way you installed Flywheel.
