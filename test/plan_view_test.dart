// Plan view: offline it states the fact and names the command that fixes it,
// exactly like every other destination.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/plan_view.dart';

void main() {
  testWidgets('Plan view offline names the command', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: PlanView(client: GatewayClient(), alive: false),
    ));
    await tester.pump();
    expect(find.textContaining('flywheel up'), findsOneWidget);
  });
}
