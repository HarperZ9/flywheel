# Articulate for JetBrains IDEs

Inline writing diagnostics in IntelliJ IDEA, PyCharm, WebStorm, GoLand, and the
rest of the JetBrains family, powered by the same Articulate language server that
backs VS Code. No custom plugin is needed: JetBrains speaks LSP through LSP4IJ,
and Articulate registers as a user-defined language server.

## Setup

1. Install the **LSP4IJ** plugin (Settings | Plugins | Marketplace | search
   "LSP4IJ").
2. Install the Articulate package for the interpreter you will point at:

   ```bash
   pip install articulate-writing        # or: pip install -e /path/to/articulate
   ```

3. Register the server: Settings | Languages & Frameworks | Language Servers |
   `+` | New Language Server, then set

   - **Name:** `Articulate`
   - **Command:** `python -m articulate.lsp_server`
     (append `--profile essay` or a mode later if you want to force one)
   - **Mappings:** add file-name patterns `*.md`, `*.markdown`, `*.txt`, `*.tex`

4. Apply. Open a Markdown or text file; tells appear as inline highlights with the
   rule id, the same warning / information / hint levels as the VS Code client.

## Why no plugin

LSP4IJ is the one-server-many-clients pattern the assessment recommended: the
server is the whole product, and every editor is a thin client over stdio. The
server runs locally with no network call. If a packaged, marketplace-installable
plugin is wanted later, it is a small Gradle IntelliJ plugin whose only job is to
register this same command through an `LanguageServerFactory`; the server code
does not change.
