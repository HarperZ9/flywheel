import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/app.dart';
import 'package:flywheel_desktop/services/gateway_process.dart';
import 'package:flywheel_desktop/services/gateway_status.dart';
import 'package:flywheel_desktop/shell/flywheel_dependencies.dart';
import 'journey_shell_harness.dart' show ShellHarness, unmount;

void main() {
  testWidgets(
    'opening installed shell starts its bundled engine without a click',
    (tester) async {
      final directory = Directory.systemTemp.createTempSync('startup-shell-');
      addTearDown(() => directory.deleteSync(recursive: true));
      final harness = ShellHarness(directory)..replyReady();
      final engine = _BundledEngine();
      final dependencies = FlywheelDependencies(
        client: harness.client,
        gateway: engine,
        journey: harness.controller,
        rowan: harness.rowan,
        code: harness.code,
        autoStartBundledEngine: true,
        status: GatewayStatusService(
          statusEndpoint: (_) async {
            if (engine.starts == 0) {
              throw const SocketException(
                'refused',
                osError: OSError('refused', 10061),
              );
            }
            return const GatewayStatusDoc({
              'schema': 'flywheel.desktop-status/v1',
              'status': 'ok',
              'compatible': true,
              'lanes_live': 0,
              'lanes_total': 0,
            });
          },
        ),
      );
      await tester.pumpWidget(
        FlywheelApp(settings: harness.settings, dependencies: dependencies),
      );
      await tester.pumpAndSettle();
      expect(engine.starts, 1);
      expect(find.text('starting bundled engine…'), findsWidgets);
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      expect(find.text('engine online · no lanes declared'), findsOneWidget);
      expect(engine.starts, 1);
      await unmount(tester);
      expect(engine.stops, 1);
      expect(tester.takeException(), isNull);
    },
  );
}

class _BundledEngine extends GatewayProcess {
  int starts = 0, stops = 0;
  @override
  Future<String?> startBundled({int port = 8799}) async {
    expect(port, 8799);
    starts++;
    return null;
  }

  @override
  Future<String?> start({int port = 8799}) async =>
      throw StateError('Automatic startup must use the bundled-only route');
  @override
  void stopIfOwned() {
    stops++;
  }
}
