# Flywheel 1.3.4

This release ships the Windows installer that 1.3.3 did not. The Python package changes only in its version number.

## Try it

```
pip install -U flywheel-verify
```

On Windows, install `Flywheel-Setup-1.3.4-x64.exe` from this release. Everything in 1.3.3 is in it, including the `raw` lane; see `RELEASE-NOTES-1.3.3.md`.

## Why there was no 1.3.3 installer

The installer build checks the frozen engine before it packages it. For 1.3.3 that check stopped with `RELAY_ROSTER_HTTP`: the engine answered `/api/lanes` with a server error.

The cause was the new `raw` lane. It has no MCP server, so the roster reads its state from a Python adapter, and it imports that adapter by the name written in the lane registry (`harness.raw_lane`). PyInstaller only bundles modules it can see imported in code, and a name inside a string is invisible to it. The frozen engine therefore had no `harness.raw_lane`, the roster raised, and the route failed. The Windows app reads its lanes from the same roster, so it could not have shown them.

A pip install was never affected, because it imports the adapter from source. That is why the 1.3.3 wheel on PyPI stays as published.

The freeze now adds every adapter module the lane registry names, with its installer module, to the engine. A new test runs on every pull request and fails when an adapter lane's modules are missing from the freeze list or from the spec. The frozen check itself runs only on a release tag, which is how this reached a tag.

## Monitor rule pack

The pre-action monitor's rule pack is unchanged from 1.3.3, so a pinned
`expected_rules_digest` stays valid. `flywheel monitor owner` prints it as
`installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```

## Limits

- The new test checks the freeze list against the registry and the spec. It does not freeze the engine, so a module reached by name some other way is still caught only by the tag-time check.
- The 1.3.3 tag and its PyPI package are unchanged. No 1.3.3 installer exists.
