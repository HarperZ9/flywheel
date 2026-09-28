# Security policy

## Reporting a vulnerability

Report a vulnerability in Flywheel Verify privately through GitHub's private vulnerability reporting for the flywheel repository: https://github.com/HarperZ9/flywheel/security/advisories/new

Please include the plugin version, what you ran, and what happened. Do not open a public issue for a security problem.

## What is in scope

- The check server started by this plugin (`flywheel-check-mcp` from the `flywheel-verify` package), including how `verify_bundle` handles a bundle it did not build.
- The plugin files: the manifest, the MCP start command, the skill, and the sample data.

## What the server is built to refuse

- Reading outside the project folder or the plugin's examples folder, including through `..`, a symlink, or a Windows junction.
- Running a program named in a contract.
- Writing a file or opening a network connection.

A report that any of these happens is in scope and wanted.
