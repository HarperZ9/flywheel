# Security

Report a security problem in Articulate Writing privately through GitHub's
private vulnerability reporting at
https://github.com/HarperZ9/articulate/security/advisories/new. Please do not
open a public issue for it. Include the plugin version (`articulate.doctor`
reports it), your operating system and Python version, and the smallest input
that shows the problem.

## What counts

- A network connection opened by the plugin. The calling model already reads
  submitted text as part of your conversation.
- A file created or changed anywhere, or read outside the plugin folder and the
  Python installation.
- A program started by the plugin, or code run through its launcher.
- Instructions inside document text causing actions outside the requested
  check or host-edit protocol.
- An input that crashes the server or keeps it busy for a long time.

## After you report

Each report is answered in its advisory thread. A fix ships in a new plugin
version, and the advisory is published once the fix is available. The latest
plugin version receives security fixes.
