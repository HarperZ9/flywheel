import 'dart:convert';

import 'gateway_process.dart';

enum ClientConfigFormat { codexToml, mcpJson }

/// A configuration preview, not a connection probe or permission grant.
/// The supplied resolver checks bundle presence; formatting itself is pure.
class ClientConnectionPreview {
  ClientConnectionPreview.fromBundledEngine(String? path)
      : enginePath = _localAbsolutePath(path) ? path : null;

  factory ClientConnectionPreview.resolve(
          {String? Function()? bundledEngine}) =>
      ClientConnectionPreview.fromBundledEngine(
          (bundledEngine ?? GatewayProcess.bundledEngine)());

  final String? enginePath;
  bool get available => enginePath != null;

  String get reason => available
      ? 'Bundled engine found. Connection not tested.'
      : 'The bundled engine is unavailable. Install or repair Flywheel '
          'with its bundled engine, then reopen Plugins.';

  static const _arguments = [
    '--bundled-lane-mcp',
    'articulate',
    '--local-only',
  ];

  String? snippet(ClientConfigFormat format) {
    final path = enginePath;
    if (path == null) return null;
    switch (format) {
      case ClientConfigFormat.codexToml:
        // JSON quoting is valid TOML basic-string quoting for these paths.
        // Control characters are rejected before serialization.
        return '[mcp_servers.flywheel-articulate]\n'
            'command = ${jsonEncode(path)}\n'
            'args = [${_arguments.map(jsonEncode).join(', ')}]\n';
      case ClientConfigFormat.mcpJson:
        return '${const JsonEncoder.withIndent('  ').convert({
              'mcpServers': {
                'flywheel-articulate': {'command': path, 'args': _arguments},
              },
            })}\n';
    }
  }

  static bool _localAbsolutePath(String? path) {
    if (path == null || RegExp(r'[\x00-\x1f\x7f]').hasMatch(path)) return false;
    if (path.startsWith(r'\\') || path.startsWith('//')) return false;
    return RegExp(r'^[A-Za-z]:[\\/]').hasMatch(path) || path.startsWith('/');
  }
}
