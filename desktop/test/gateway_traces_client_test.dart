import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_traces.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('pending confirmations are read from the trace custody route', () async {
    final seen = <String>[];
    final client = GatewayClient(
        baseUrl: 'https://gateway.invalid',
        httpClient: MockClient((request) async {
          seen.add('${request.method} ${request.url.path}');
          return http.Response(
              '{"schema":"flywheel.presence-pending/v1","pending":[{"ref":"prs_1",'
              '"kind":"export","plan_digest":"a","expires_at":1}]}',
              200);
        }));
    final pending = await client.presencePending();
    expect(seen, ['GET /api/traces/presence/pending']);
    expect(pending.single['ref'], 'prs_1');
    expect(pending.single['kind'], 'export');
  });

  test('a malformed pending list reads as empty', () async {
    final client = GatewayClient(
        baseUrl: 'https://gateway.invalid',
        httpClient:
            MockClient((request) async => http.Response('{"pending":7}', 200)));
    expect(await client.presencePending(), isEmpty);
  });
}
