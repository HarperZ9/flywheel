import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'support/bulletin_actor_approval.dart';
import 'support/bulletin_actor_exchange.dart';

void main() {
  test('ready sentinel follows successful capabilities only and is exclusive',
      () async {
    for (final ready in [false, true]) {
      final root = Directory.systemTemp.createTempSync('bulletin-ready-');
      try {
        final exchange = ActorExchange(root.path);
        final sentinel = File('${root.path}/ready.txt');
        final client = GatewayGrantClient(GatewayClient(
            baseUrl: 'http://127.0.0.1:12345',
            httpClient: MockClient((_) async {
              expect(sentinel.existsSync(), isFalse);
              return http.Response(
                  jsonEncode({
                    'schema': 'flywheel.gateway-grant-capabilities/v1',
                    'reviewed_approval': ready,
                    'proposal_list': true,
                    'proposal_read': true,
                    'durable_reject': true,
                    'review_max_bytes': 65536
                  }),
                  200);
            })));
        if (ready) {
          await announceActorReady(client, exchange);
          expect(sentinel.readAsBytesSync(),
              utf8.encode('BULLETIN_ACTOR_READY\n'));
          expect(
              () => exchange.writeReady(), throwsA(isA<ActorExchangeError>()));
        } else {
          await expectLater(announceActorReady(client, exchange),
              throwsA(isA<ActorExchangeError>()));
          expect(sentinel.existsSync(), isFalse);
        }
      } finally {
        root.deleteSync(recursive: true);
      }
    }
  });
}
