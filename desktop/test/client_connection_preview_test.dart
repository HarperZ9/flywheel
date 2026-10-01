import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/services/client_connection_preview.dart';

void main() {
  const path = r"C:\Program Files\Flywheel's tools\engine\flywheel-gateway.exe";

  test('missing bundle refuses both formats without a PATH fallback', () {
    final preview = ClientConnectionPreview.resolve(bundledEngine: () => null);
    expect(preview.available, isFalse);
    expect(preview.reason, contains('bundled engine is unavailable'));
    for (final format in ClientConfigFormat.values) {
      expect(preview.snippet(format), isNull);
    }
  });

  test('relative paths, remote paths and control characters fail closed', () {
    for (final path in [
      'flywheel.exe',
      'C:flywheel.exe',
      r'\\server\engine.exe',
      '//server/engine.exe',
      'https://example.com/engine.exe',
      'C:\\bad\npath\\engine.exe',
    ]) {
      expect(ClientConnectionPreview.fromBundledEngine(path).available, isFalse,
          reason: path);
    }
  });

  test('Windows paths round trip and restricted argv is the entire config', () {
    final preview = ClientConnectionPreview.fromBundledEngine(path);
    final json = jsonDecode(preview.snippet(ClientConfigFormat.mcpJson)!);
    expect(json, {
      'mcpServers': {
        'flywheel-articulate': {
          'command': path,
          'args': ['--bundled-lane-mcp', 'articulate', '--local-only'],
        },
      },
    });
    final toml = preview.snippet(ClientConfigFormat.codexToml)!;
    expect(toml.split('\n'), [
      '[mcp_servers.flywheel-articulate]',
      'command = ${jsonEncode(path)}',
      'args = ["--bundled-lane-mcp", "articulate", "--local-only"]',
      '',
    ]);
    expect(
        jsonDecode(toml.split('\n')[1].substring('command = '.length)), path);
    expect(preview.reason, contains('Connection not tested'));
  });

  test('exports contain no credentials, endpoints or automatic approvals', () {
    final preview = ClientConnectionPreview.fromBundledEngine(path);
    for (final format in ClientConfigFormat.values) {
      final snippet = preview.snippet(format)!;
      for (final forbidden in [
        'env',
        'token',
        'key',
        'url',
        'http',
        'approval',
        'allow',
        'python',
        'node',
        'npx',
        'write',
        'shell',
      ]) {
        expect(snippet.toLowerCase(), isNot(contains(forbidden)));
      }
    }
  });
}
