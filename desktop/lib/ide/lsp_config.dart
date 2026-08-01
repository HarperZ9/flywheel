// lsp_config.dart — which language server answers for which file, plus the
// offset/position arithmetic the editor needs. The server must already be
// installed; a missing one is a named error from the engine, never a
// silent fallback.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class LspServer {
  final String languageId;
  final List<String> command;
  const LspServer(this.languageId, this.command);
}

const Map<String, LspServer> _byExtension = {
  'dart': LspServer('dart', ['dart', 'language-server', '--protocol=lsp']),
  'py': LspServer('python', ['pyright-langserver', '--stdio']),
  'ts': LspServer('typescript', ['typescript-language-server', '--stdio']),
  'tsx': LspServer('typescriptreact', ['typescript-language-server', '--stdio']),
  'js': LspServer('javascript', ['typescript-language-server', '--stdio']),
  'jsx': LspServer('javascriptreact', ['typescript-language-server', '--stdio']),
};

LspServer? lspServerFor(String path) {
  final dot = path.lastIndexOf('.');
  if (dot < 0) return null;
  return _byExtension[path.substring(dot + 1).toLowerCase()];
}

/// Character offset -> zero-based (line, character).
(int, int) positionOf(String text, int offset) {
  final clamped = offset.clamp(0, text.length);
  var line = 0, lineStart = 0;
  for (var i = 0; i < clamped; i++) {
    if (text.codeUnitAt(i) == 0x0A) {
      line++;
      lineStart = i + 1;
    }
  }
  return (line, clamped - lineStart);
}

/// Zero-based (line, character) -> character offset.
int offsetOf(String text, int line, int character) {
  var current = 0, start = 0;
  while (current < line) {
    final nl = text.indexOf('\n', start);
    if (nl < 0) return text.length;
    start = nl + 1;
    current++;
  }
  return (start + character).clamp(0, text.length);
}

/// Parse an LSP definition result (Location | Location[] | LocationLink[])
/// into (file path, line, character), or null when the server had nothing.
({String path, int line, int character})? parseDefinition(dynamic result) {
  dynamic loc = result;
  if (loc is List) {
    if (loc.isEmpty) return null;
    loc = loc.first;
  }
  if (loc is! Map) return null;
  final uri = loc['uri'] ?? loc['targetUri'];
  final range = loc['range'] ?? loc['targetSelectionRange'];
  if (uri is! String || range is! Map) return null;
  final start = range['start'];
  if (start is! Map) return null;
  var path = Uri.parse(uri).toFilePath(windows: true);
  return (
    path: path,
    line: (start['line'] ?? 0) as int,
    character: (start['character'] ?? 0) as int
  );
}

/// The Code view's definition lookup: server selection, position math, the
/// engine round trip, and honest failure messages in one place.
class DefinitionResult {
  final ({String path, int line, int character})? target;
  final String message;
  const DefinitionResult(this.target, this.message);
}

Future<DefinitionResult> resolveDefinition(
    dynamic client, dynamic file, String root) async {
  final server = lspServerFor(file.path as String);
  if (server == null) {
    return DefinitionResult(null, 'no language server mapped for this file');
  }
  final text = file.controller.text as String;
  final sel = file.controller.selection;
  final (line, character) =
      positionOf(text, (sel.isValid ? sel.baseOffset : 0) as int);
  try {
    final out = await client.lspQuery(
      command: server.command,
      root: root,
      file: file.path as String,
      text: text,
      languageId: server.languageId,
      method: 'definition',
      line: line,
      character: character,
    );
    if (out['error'] != null) return DefinitionResult(null, '${out['error']}');
    final target = parseDefinition(out['result']);
    if (target == null) return DefinitionResult(null, 'no definition found');
    return DefinitionResult(target, 'ok');
  } catch (e) {
    return DefinitionResult(null, 'definition failed: $e');
  }
}

/// Parse an LSP references result (Location[]) into jump targets.
List<({String path, int line, int character})> parseLocations(dynamic result) {
  if (result is! List) return const [];
  final out = <({String path, int line, int character})>[];
  for (final loc in result) {
    final one = parseDefinition(loc);
    if (one != null) out.add(one);
  }
  return out;
}

/// References lookup mirroring resolveDefinition.
Future<({List<({String path, int line, int character})> targets, String message})>
    resolveReferences(dynamic client, dynamic file, String root) async {
  final server = lspServerFor(file.path as String);
  if (server == null) {
    return (
      targets: const <({String path, int line, int character})>[],
      message: 'no language server mapped for this file'
    );
  }
  final text = file.controller.text as String;
  final sel = file.controller.selection;
  final (line, character) =
      positionOf(text, (sel.isValid ? sel.baseOffset : 0) as int);
  try {
    final out = await client.lspQuery(
      command: server.command,
      root: root,
      file: file.path as String,
      text: text,
      languageId: server.languageId,
      method: 'references',
      line: line,
      character: character,
    );
    if (out['error'] != null) return (targets: const <({String path, int line, int character})>[], message: '${out['error']}');
    final targets = parseLocations(out['result']);
    return (
      targets: targets,
      message: targets.isEmpty ? 'no references found' : '${targets.length} references'
    );
  } catch (e) {
    return (targets: const <({String path, int line, int character})>[], message: 'references failed: $e');
  }
}

/// On-save diagnostics: count + first messages for the status line.
Future<String?> resolveDiagnostics(
    dynamic client, dynamic file, String root) async {
  final server = lspServerFor(file.path as String);
  if (server == null) return null;
  try {
    final out = await client.lspQuery(
      command: server.command,
      root: root,
      file: file.path as String,
      text: file.controller.text as String,
      languageId: server.languageId,
      method: 'diagnostics',
      line: 0,
      character: 0,
    );
    if (out['error'] != null) return '${out['error']}';
    final diags = (out['diagnostics'] is List)
        ? (out['diagnostics'] as List)
        : const [];
    if (diags.isEmpty) return 'no problems reported';
    final first = diags.first is Map ? '${(diags.first as Map)['message']}' : '';
    return '${diags.length} problem${diags.length == 1 ? '' : 's'}: $first';
  } catch (e) {
    return 'diagnostics failed: $e';
  }
}

/// The references picker: a bottom sheet of jump targets.
void showReferencesSheet(
    BuildContext context,
    List<({String path, int line, int character})> targets,
    void Function(({String path, int line, int character})) onJump) {
  showModalBottomSheet(
    context: context,
    backgroundColor: Theme.of(context).extension<FwTokens>()!.ground,
    builder: (ctx) {
      final t = Theme.of(ctx).extension<FwTokens>()!;
      return ListView(
        padding: const EdgeInsets.all(FwLayout.s4),
        children: [
          const Kicker('references', hot: true),
          const SizedBox(height: FwLayout.s2),
          for (final target in targets)
            ListTile(
              dense: true,
              title: Text(
                  '${target.path.split(RegExp(r"[\\/]")).last}:${target.line + 1}',
                  style: fwMono(t, size: 12)),
              subtitle: Text(target.path,
                  overflow: TextOverflow.ellipsis,
                  style: fwMono(t, size: 10.5, color: t.inkFaint)),
              onTap: () {
                Navigator.of(ctx).pop();
                onJump(target);
              },
            ),
        ],
      );
    },
  );
}
