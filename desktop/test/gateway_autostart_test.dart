import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/connection_state.dart';
import 'package:flywheel_desktop/services/gateway_process.dart';
import 'package:flywheel_desktop/services/gateway_status.dart';
import 'package:flywheel_desktop/shell/gateway_status_coordinator.dart';

const refused = SocketException('synthetic refusal',
    osError: OSError('synthetic refusal', 10061));

void main() {
  test('observed Windows HTTP refusal 1225 starts once', () async {
    var starts = 0;
    final c = makeCoordinator(
        () async => throw const SocketException('refused',
            osError: OSError('refused', 1225)), autoStart: () async {
      starts++;
      return null;
    });
    addTearDown(c.dispose);
    await c.poll();
    await c.poll();
    expect(starts, 1);
  });

  test('disposal in start notification prevents even an orphan launch',
      () async {
    var starts = 0;
    final c = makeCoordinator(() async => throw refused, autoStart: () async {
      starts++;
      return null;
    });
    final reported = <FlutterErrorDetails>[];
    final previous = FlutterError.onError;
    FlutterError.onError = reported.add;
    addTearDown(() => FlutterError.onError = previous);
    c.addListener(() {
      if (c.message == 'starting bundled engine…') c.dispose();
    });
    await c.poll();
    // ChangeNotifier rejects disposal during notification in debug builds;
    // the coordinator has still observed disposal and must not start work.
    expect(reported, hasLength(1));
    expect(reported.single.exception.toString(), contains('dispose()'));
    expect(starts, 0);
  });

  test('confirmed local refusal starts once and next poll recovers', () async {
    var starts = 0, ready = 0, available = false;
    final coordinator = makeCoordinator(
      () async {
        if (!available) throw refused;
        return healthy;
      },
      autoStart: () async {
        starts++;
        available = true;
        return null;
      },
      onReady: () async {
        ready++;
      },
    );
    addTearDown(coordinator.dispose);
    await coordinator.poll();
    expect(starts, 1);
    expect(coordinator.alive, isFalse, reason: 'spawn is not readiness');
    await coordinator.poll();
    expect(coordinator.alive, isTrue);
    expect(ready, 1);
    available = false;
    await coordinator.poll();
    expect(starts, 1, reason: 'engine exit must not create a respawn loop');
  });

  for (final outcome in <String, Future<GatewayStatusOutcome> Function()>{
    'auth': () async => const GatewayStatusFailure(401),
    'server error': () async => const GatewayStatusFailure(500),
    'unknown failure': () async => const GatewayStatusFailure(0),
    'invalid schema': () async => const GatewayStatusDoc({}),
    'mismatch': () async => const GatewayStatusDoc({
          'schema': 'flywheel.desktop-status/v1',
          'compatible': false,
        }),
    'timeout': () async => throw TimeoutException('synthetic timeout'),
    'permission': () async => throw const SocketException('denied',
        osError: OSError('denied', 10013)),
  }.entries) {
    test('${outcome.key} never starts another engine', () async {
      var starts = 0;
      final c = makeCoordinator(outcome.value, autoStart: () async {
        starts++;
        return null;
      });
      addTearDown(c.dispose);
      await c.poll();
      await c.poll();
      expect(starts, 0);
    });
  }

  test('remote refusal does not launch a local engine', () async {
    var starts = 0;
    final c = makeCoordinator(() async => throw refused,
        endpoint: 'https://example.invalid/api/desktop/status',
        autoStart: () async {
      starts++;
      return null;
    });
    addTearDown(c.dispose);
    await c.poll();
    expect(starts, 0);
  });

  test('no bundled-start callback preserves manual-only operation', () async {
    final c = makeCoordinator(() async => throw refused);
    addTearDown(c.dispose);
    await c.poll();
    expect(c.connection.phase, ConnectionPhase.offline);
    expect(c.startError, isNull);
  });

  test('failed automatic start remains visible and does not repeat', () async {
    var starts = 0;
    final c = makeCoordinator(() async => throw refused, autoStart: () async {
      starts++;
      return 'Bundled engine unavailable';
    });
    addTearDown(c.dispose);
    await c.poll();
    await c.poll();
    expect(starts, 1);
    expect(c.startError, 'Bundled engine unavailable');
  });

  test('disposed pending start retains orphan cleanup', () async {
    final started = Completer<void>(), launch = Completer<String?>();
    var cleaned = 0;
    final c = makeCoordinator(() async => throw refused, autoStart: () {
      started.complete();
      return launch.future;
    }, onOrphanStart: () {
      cleaned++;
    });
    final poll = c.poll();
    await started.future;
    c.dispose();
    launch.complete(null);
    await poll;
    expect(cleaned, 1);
  });

  test('vanished bundle cannot fall back to PATH during automatic start',
      () async {
    var launches = 0;
    final process = GatewayProcess(
      bundledEngineResolver: () => null,
      processStarter: (exe, args, {required mode, required runInShell}) async {
        launches++;
        throw StateError('must not launch');
      },
    );
    expect(await process.startBundled(), isNotNull);
    expect(launches, 0);
  });
}

const healthy = GatewayStatusDoc({
  'schema': 'flywheel.desktop-status/v1',
  'status': 'ok',
  'compatible': true,
  'lanes_live': 0,
  'lanes_total': 0,
});

GatewayStatusCoordinator makeCoordinator(
  Future<GatewayStatusOutcome> Function() read, {
  Future<String?> Function()? autoStart,
  Future<void> Function()? onReady,
  void Function()? onOrphanStart,
  String endpoint = 'http://127.0.0.1:8799/api/desktop/status',
}) =>
    GatewayStatusCoordinator(
      client: GatewayClient(
          httpClient: MockClient((r) async => http.Response(
              r.url.path == '/api/lanes'
                  ? '{"n_lanes":0,"by_status":{},"lanes":[]}'
                  : '{}',
              200))),
      status: GatewayStatusService(
          statusEndpoint: (_) => read(), endpoint: () => Uri.parse(endpoint)),
      startEngine: () async =>
          throw StateError('manual start was not requested'),
      autoStartEngine: autoStart,
      onReady: onReady,
      onOrphanStart: onOrphanStart,
    );
