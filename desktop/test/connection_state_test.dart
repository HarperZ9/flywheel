// Connection truth and scale composition: the app must MULTIPLY the
// operating system's text scaling by the user's in-app scale, never
// replace one with the other, and the shell must distinguish typed
// connection phases instead of one boolean alive flag.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/app.dart';
import 'package:flywheel_desktop/models/connection_state.dart';
import 'package:flywheel_desktop/services/gateway_status.dart';
import 'package:flywheel_desktop/services/settings.dart';

void main() {
  testWidgets('system 2.0 scaling combined with user 1.2 yields 2.4',
      (tester) async {
    tester.view.physicalSize = const Size(2400, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(() => tester.platformDispatcher.textScaleFactorTestValue = 1.0);
    final settings = DesktopSettings()..uiScale = 1.2;
    await tester.pumpWidget(FlywheelApp(settings: settings));
    await tester.pump();

    final scaler = MediaQuery.textScalerOf(
        tester.element(find.text('Flywheel').first));
    expect(scaler.scale(14.5), closeTo(14.5 * 2.4, 0.01),
        reason: 'system scaling must compose with, not be replaced by, '
            'the in-app scale');
  });

  group('ConnectionStatus', () {
    test('a healthy status doc reads online', () {
      final s = ConnectionStatus.fromStatusDoc({
        'schema': 'flywheel.desktop-status/v1',
        'status': 'ok',
        'api_version': 1,
        'lanes_live': 3,
        'lanes_total': 3,
        'compatible': true,
      });
      expect(s.phase, ConnectionPhase.online);
      expect(s.alive, isTrue);
      expect(s.detail, contains('3/3'));
    });

    test('a partial roster reads degraded, not offline', () {
      final s = ConnectionStatus.fromStatusDoc({
        'schema': 'flywheel.desktop-status/v1',
        'status': 'degraded',
        'lanes_live': 1,
        'lanes_total': 3,
        'compatible': true,
      });
      expect(s.phase, ConnectionPhase.degraded);
      expect(s.alive, isTrue,
          reason: 'a degraded engine still serves; it is not offline');
    });

    test('an incompatible client reads versionMismatch', () {
      final s = ConnectionStatus.fromStatusDoc({
        'schema': 'flywheel.desktop-status/v1',
        'status': 'incompatible',
        'compatible': false,
        'lanes_live': 3,
        'lanes_total': 3,
      });
      expect(s.phase, ConnectionPhase.versionMismatch);
      expect(s.alive, isFalse);
    });

    test('missing fields degrade to a typed offline, never a crash', () {
      final s = ConnectionStatus.fromStatusDoc({});
      expect(s.phase, ConnectionPhase.offline);
    });

    test('fixed phases cover the spec matrix', () {
      expect(ConnectionPhase.values.length, 6);
      expect(ConnectionPhase.starting, isNotNull);
      expect(ConnectionPhase.authRequired, isNotNull);
    });
  });

  group('GatewayStatusService', () {
    test('a 401 maps to authRequired', () async {
      final service = GatewayStatusService(
        statusEndpoint: (_) async => GatewayStatusFailure(401),
      );
      expect((await service.probe()).phase, ConnectionPhase.authRequired);
    });

    test('no response maps to offline', () async {
      final service = GatewayStatusService(
        statusEndpoint: (_) async => GatewayStatusFailure(0),
      );
      expect((await service.probe()).phase, ConnectionPhase.offline);
    });

    test('a healthy doc maps through the typed model', () async {
      final service = GatewayStatusService(
        statusEndpoint: (_) async => GatewayStatusDoc({
          'schema': 'flywheel.desktop-status/v1',
          'status': 'degraded',
          'lanes_live': 1,
          'lanes_total': 2,
          'compatible': true,
        }),
      );
      final s = await service.probe();
      expect(s.phase, ConnectionPhase.degraded);
      expect(s.detail, contains('1/2'));
    });
  });
}
