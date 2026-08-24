import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/plan_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/forge_panel.dart';
import 'package:flywheel_desktop/widgets/plan_cards.dart';

Map<String, dynamic> _prp() => {
      'schema': 'flywheel.prp/v2',
      'goal': 'implement sort that passes tests',
      'task_type': 'code',
      'intent_sha256': '',
      'architecture_sha256': '',
      'confidence': 8,
      'external_gate_ratio': '0.500',
      'gate_counts': {'checkable': 1, 'total': 2},
      'well_posed': true,
      'validation_gates': [
        {'check': 'pytest -q passes', 'externally_checkable': true},
        {'check': 'review the output', 'externally_checkable': false},
      ],
      'prompt':
          'Labels describe who could check; no gate is claimed run or passed.',
      'prp_id': '0123456789abcdef',
    };

Widget _app(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('plan card renders neutral checkability and criterion copy',
      (tester) async {
    await tester
        .pumpWidget(_app(ForgedPlanCard(plan: ForgedPlan.fromJson(_prp()))));
    expect(find.text('checkable'), findsOneWidget);
    expect(find.text('manual'), findsOneWidget);
    expect(find.text('criterion stated'), findsOneWidget);
    expect(find.text('oracle'), findsNothing);
    expect(find.text('verified'), findsNothing);
    expect(find.text('unverifiable'), findsNothing);
    expect(find.textContaining('no gate is claimed run or passed'),
        findsOneWidget);
  });

  testWidgets('studio forge does not turn checkability into a verdict',
      (tester) async {
    final client = GatewayClient(
        baseUrl: 'https://gateway.invalid',
        httpClient:
            MockClient((_) async => http.Response(jsonEncode(_prp()), 200)));
    // The forge dispatches only through an approved grant now; the scope
    // stands in for the approval flow so the test exercises the panel's
    // wiring and its truth copy, not the grant sheet itself.
    await tester.pumpWidget(_app(GatewayOperationScope(
      authorize: (context, operation, currentOperation, dispatch) async {
        final body = Map<String, dynamic>.from(operation.finalBody(
            GatewayJourneyBinding('jrn_${'a' * 32}', 'a' * 64),
            'gnt_${'a' * 32}'));
        return await dispatch(body);
      },
      child: ForgePanel(client: client),
    )));
    await tester.enterText(find.byType(TextField), 'implement sort');
    await tester.tap(find.text('Forge'));
    await tester.pumpAndSettle();
    expect(find.textContaining('checkable gates 50%'), findsOneWidget);
    expect(find.text('criterion stated'), findsOneWidget);
    expect(find.text('verified'), findsNothing);
    expect(find.textContaining('oracle'), findsNothing);
  });
}
