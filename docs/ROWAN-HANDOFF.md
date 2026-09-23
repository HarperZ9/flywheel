# Take a Rowan run elsewhere

A finished Rowan run exports as a Markdown brief that any other agent can read,
so the task continues there without being explained again. On the Rowan card,
**Copy handoff brief** puts it on the clipboard. The engine serves it to the
run's owner at `GET /api/operations/{operation_ref}/handoff`.

## What the brief holds

- **Goal**: the task as it was given, quoted, up to 60 lines and 8,000
  characters.
- **Where it ended**: the run state and failure reason, the completion split
  (verified, claimed, failed) and whether the run budget stopped it.
- **Deliverables**: the final answer first, then each file the run wrote or a
  command changed, with its mark and the check behind it (see
  `docs/VERIFIED-COMPLETION.md`). Up to 20 lines, then a count of the rest,
  including any the completion record itself left out.
- **Commands run**: up to 20, then a count of the rest.
- **Steps the model stated**: the model's own words per step, labelled as
  unchecked. A step that called a tool shows the tool's name and path only;
  the arguments, which can hold file content, are left out.
- **Open items**: work that is claimed and unverified, checks that failed, an
  unfinished run, a success claim with no check behind it, and success
  reports from the provider or the CLI that came with a rate limit, quota,
  billing, sign-in or service-overloaded error in their own fields.
- **Final answer**: quoted, labelled as the model's words, up to 60 lines and
  40,000 characters.
- **Receipts**: the operation, Journey and private trace references, the trace
  head hash, the ledger checkpoint and the run verdict.

The response also carries the trace reference, record count and head hash the
brief was rendered from. The engine refuses the brief when the trace no longer
matches the run's recorded result.

## The marks it shows

The brief shows the completion marks only after the gateway recheck the Rowan
card uses. When the recheck refuses the record, for example because the run
was stopped at its deadline after the worker recorded a verified answer, the
brief says "Completion: unverifiable" with the reason, and each deliverable
reads "recorded as verified, not confirmed" instead of a mark.

## What stays on the machine

The brief is written to be pasted into another provider's agent, so before it
leaves the engine:

- Credentials found by pattern are replaced with `[credential omitted]`. The
  patterns cover:
  - URL user info, and the secret in `curl -u name:secret` or `--user`.
  - Password flags such as `--password`, `--http-password`, `--passphrase`,
    `-storepass` and OpenSSL's `-passin`.
  - The password flag of `mysql -p`, `sshpass -p`, `docker login -p` and the
    other registry logins, `redis-cli -a`, `mongosh -p`, `sqlcmd -P` and the
    LDAP tools' `-w`. Each is read only on a line that runs its command.
  - Assignments such as `API_KEY=...`, `PGPASSWORD=...` and `DB_PASS=...`.
  - Bearer tokens, and the Docker, GitLab, GitHub, npm, Hugging Face and PyPI
    token shapes.
  - A keyword followed by a value that looks like a credential, with up to two
    linking words between them: `password hunter2pass` or
    `the password is Hunter2pass!`.
- A line that still matches a credential pattern after that is withheld whole.
- The workspace root is written as `<workspace>`, and any other host path as
  `[host path omitted]`. UNC paths such as `\\server\share` count as host
  paths.
- Paths and commands are single-line code spans, so a file name cannot start a
  line of its own.
- Text is cut before it is redacted, with 512 characters of margin past the
  cut. Redaction time stays bounded by what the brief can show, and a
  credential that straddles the cut is still replaced whole.
- A quote that is cut ends with a line saying how many lines and characters
  are left in the private trace.

## Limits

- The brief is a plain export of one run. Nothing is re-run or re-checked when
  it is exported; the marks are the ones recorded at the end of the run.
- File contents are not included. The next agent needs the workspace to
  continue from the files themselves.
- Redaction is a pattern list. A credential written in a shape it does not
  know, such as an all-letter password after the word "password", is not
  caught. A value of digits only, or `true` or `false`, after a name such as
  `DB_PASS` is kept, since it is more often a count or a switch. Read the brief
  before pasting it anywhere.
- The format is plain Markdown for any agent. Rendering context for a
  particular provider is not part of this export.
- Only the run's owner can read it, through the same authorization as the
  private trace.
