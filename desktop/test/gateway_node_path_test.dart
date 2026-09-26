// The Node path setting on the lane client: one GET, one POST, the engine's
// answer returned as sent. The picker that calls these lands with the lane
// console (WP9b); this holds the wire shape the engine route expects.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';

void main() {
  test('nodePath reads the setting and setNodePath posts the chosen file',
      () async {
    final seen = <String>[];
    final client = GatewayClient(httpClient: MockClient((r) async {
      seen.add('${r.method} ${r.url.path} ${r.body}');
      return http.Response(
          jsonEncode({'id': 'node', 'met': true, 'copy': 'Node v22.1.0 at x.'}),
          200);
    }));
    final read = await client.nodePath();
    final chosen = await client.setNodePath(r'C:\tools\node.exe');
    final cleared = await client.setNodePath(null);
    expect(seen, [
      'GET /api/settings/node_path ',
      'POST /api/settings/node_path {"path":"C:\\\\tools\\\\node.exe"}',
      'POST /api/settings/node_path {"path":null}',
    ]);
    expect(read['met'], isTrue);
    expect(chosen['id'], 'node');
    expect(cleared['id'], 'node');
  });
}
