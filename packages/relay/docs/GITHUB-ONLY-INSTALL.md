# GitHub-only install guidance

Relay publishes to PyPI as `flywheel-relay`. The public PyPI namespace
`relay-agent` belongs to an unrelated project and is not the HarperZ9 Relay
distribution. Do not run `pip install relay-agent` and do not document it as a
Relay install path.

`pip install flywheel-relay` is the ordinary path and carries PEP 740
attestations. The GitHub-pinned paths below exist for anyone who would rather
verify the bytes themselves than trust the index.

## Source pin

Replace `<accepted-commit>` with the reviewed commit SHA from
`https://github.com/HarperZ9/relay`.

```bash
python -m pip install "flywheel-relay @ git+https://github.com/HarperZ9/relay.git@<accepted-commit>"
```

This installs the same distribution, `flywheel-relay`, with the source pinned to
HarperZ9 GitHub. The commit SHA is the authority; omitting it
turns the install into a moving target.

## Release wheel

After the GitHub Release exists, download the wheel and SHA-256 receipt from the
release page. Example 0.7.0 release asset names:

```text
tag: v0.7.0
wheel: flywheel_relay-0.7.0-py3-none-any.whl
sdist: flywheel_relay-0.7.0.tar.gz
sha256: <release-sha256-from-SHA256SUMS.txt>
url: https://github.com/HarperZ9/relay/releases/download/v0.7.0/<asset-name>
```

Verify the hash before installing. Do not continue to `pip install` if the wheel has no checksum line or the computed hash differs. Example in PowerShell:

```powershell
& {
  $ErrorActionPreference = "Stop"
  $wheel = "flywheel_relay-0.7.0-py3-none-any.whl"
  $pattern = "^[0-9a-fA-F]{64}\s+$([regex]::Escape($wheel))$"
  $matches = @(Select-String -LiteralPath ".\SHA256SUMS.txt" -Pattern $pattern)
  if ($matches.Count -ne 1) { throw "expected exactly one SHA256SUMS entry for $wheel; found $($matches.Count)" }
  $expected = ($matches[0].Line -split "\s+")[0].ToLowerInvariant()
  $actual = (Get-FileHash -LiteralPath ".\$wheel" -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected) { throw "sha256 mismatch for $wheel" }
  python -m pip install --no-index ".\$wheel"
}
```

This path does not query PyPI. If a future release moves to a new verified
package namespace, update this page, tools/check_release_metadata.py and the
release notes before publishing. That guard is what makes this page stay true.
