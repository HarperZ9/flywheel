import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

function startClient(): void {
  const cfg = vscode.workspace.getConfiguration("articulate");
  if (!cfg.get<boolean>("enable", true)) {
    return;
  }
  const python = cfg.get<string>("pythonPath", "python");
  const profile = (cfg.get<string>("profile", "") || "").trim();

  const args = ["-m", "articulate.lsp_server"];
  if (profile.length > 0) {
    args.push("--profile", profile);
  }

  const serverOptions: ServerOptions = {
    run: { command: python, args, transport: TransportKind.stdio },
    debug: { command: python, args, transport: TransportKind.stdio },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "markdown" },
      { scheme: "file", language: "plaintext" },
      { scheme: "file", language: "latex" },
    ],
    synchronize: { configurationSection: "articulate" },
  };

  client = new LanguageClient(
    "articulate",
    "Articulate",
    serverOptions,
    clientOptions,
  );
  client.start();
}

export function activate(context: vscode.ExtensionContext): void {
  startClient();
  if (client) {
    context.subscriptions.push(client);
  }

  // Restart the server when a relevant setting changes.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (
        e.affectsConfiguration("articulate.pythonPath") ||
        e.affectsConfiguration("articulate.profile") ||
        e.affectsConfiguration("articulate.enable")
      ) {
        if (client) {
          await client.stop();
          client = undefined;
        }
        startClient();
        if (client) {
          context.subscriptions.push(client);
        }
      }
    }),
  );
}

export function deactivate(): Thenable<void> | undefined {
  return client ? client.stop() : undefined;
}
