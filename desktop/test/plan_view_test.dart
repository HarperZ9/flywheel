// Plan view: offline it states the fact and names the command that fixes it,
// exactly like every other destination.
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/plan_view.dart';
import 'package:flywheel_desktop/widgets/plan_run_controls.dart';

void main() {
  testWidgets('Plan view offline names the command', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: PlanView(
          client: GatewayClient(), alive: false, settings: DesktopSettings()),
    ));
    await tester.pump();
    expect(find.textContaining('flywheel up'), findsOneWidget);
  });

  test('Plan run status copy does not claim forged gates executed', () {
    expect(planRunCompletionCopy,
        'Run recorded. This receipt binds the forged contract; it does not say the listed gates ran or passed.');
    expect(planRunDriftCopy,
        'Run blocked: this plan no longer matches its stored forge contract. Review it and forge again.');
  });
}
