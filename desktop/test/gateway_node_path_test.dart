// The Node path setting on the lane client: one GET, the engine's answer
// returned as sent. Choosing node.exe is a granted action (settings.node_path)
// that the lane console sends through the grant flow (WP9b), so the client
// has no ungranted setter.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';

void main() {
  test('nodePath reads the setting and sends nothing else', () async {
    final seen = <String>[];
    final client = GatewayClient(httpClient: MockClient((r) async {
      seen.add('${r.method} ${r.url.path} ${r.body}');
      return http.Response(
          jsonEncode({'id': 'node', 'met': true, 'copy': 'Node v22.1.0 at x.'}),
          200);
    }));
    final read = await client.nodePath();
    expect(seen, ['GET /api/settings/node_path ']);
    expect(read['met'], isTrue);
  });
}
