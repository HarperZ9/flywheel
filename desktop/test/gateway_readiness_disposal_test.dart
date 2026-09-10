import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/lane_readiness.dart';
import 'package:flywheel_desktop/services/gateway_status.dart';
import 'package:flywheel_desktop/shell/gateway_status_coordinator.dart';

void main() {
  test('explicit null lane count stays unknown', () {
    expect(laneReadinessDetail(1, {'live': 1, 'missing': null}),
        contains('unknown'));
    expect(laneReadinessDetail(1, {'live': 1}), '1/1 lanes live');
  });

  test('disposed ready wait cannot start roster or world requests', () async {
    final entered = Completer<void>();
    final release = Completer<void>();
    final requests = <String>[];
    final client = GatewayClient(httpClient: MockClient((r) async {
      requests.add(r.url.path);
      return http.Response(
          r.url.path == '/api/lanes'
              ? '{"n_lanes":0,"by_status":{},"lanes":[]}'
              : '{}',
          200);
    }));
    final coordinator = GatewayStatusCoordinator(
      client: client,
      status: GatewayStatusService(
          statusEndpoint: (_) async => const GatewayStatusDoc({
                'schema': 'flywheel.desktop-status/v1',
                'status': 'ok',
                'compatible': true,
                'lanes_live': 0,
                'lanes_total': 0
              })),
      startEngine: () async => null,
      onReady: () async {
        entered.complete();
        await release.future;
      },
    );
    final polling = coordinator.poll();
    await entered.future;
    coordinator.dispose();
    release.complete();
    await polling;
    expect(requests, isEmpty);
  });

  test('dispose while reading lanes cannot start world request', () async {
    final entered = Completer<void>();
    final response = Completer<http.Response>();
    final requests = <String>[];
    final client = GatewayClient(httpClient: MockClient((r) async {
      requests.add(r.url.path);
      entered.complete();
      return response.future;
    }));
    final coordinator = GatewayStatusCoordinator(
      client: client,
      status: GatewayStatusService(
          statusEndpoint: (_) async => const GatewayStatusDoc({
                'schema': 'flywheel.desktop-status/v1',
                'status': 'ok',
                'compatible': true,
                'lanes_live': 0,
                'lanes_total': 0
              })),
      startEngine: () async => null,
    );
    final polling = coordinator.poll();
    await entered.future;
    coordinator.dispose();
    response.complete(http.Response('{"n_lanes":0,"by_status":{}}', 200));
    await polling;
    expect(requests, ['/api/lanes']);
  });
}
