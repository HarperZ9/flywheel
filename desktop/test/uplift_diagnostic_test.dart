import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/uplift_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/uplift_view.dart';

void main() {
  final oldDelta = <String, dynamic>{
    'provider': 'legacy-model', 'uplift': 0.8,
    'newcombe_95': [0.6, 0.9], 'includes_zero': false,
    'note': 'measured uplift',
  };
  test('old separated interval cannot upgrade a retry diagnostic', () {
    expect(UpliftDelta.fromJson(oldDelta).verdict, 'unverifiable');
    expect(UpliftDelta.fromJson({...oldDelta, 'uplift': -0.8}).isRegression,
        isFalse);
  });
  testWidgets('historical gateway result displays method limit and denominator',
      (tester) async {
    final client = GatewayClient(httpClient: MockClient((request) async {
      expect(request.url.path, '/api/uplift');
      return http.Response(jsonEncode({
        'runs': [{}],
        'latest': {
          'n_candidates': 4, 'comparison_key': 'uplift:legacy',
          'deltas': [oldDelta],
          'rows': [{
            'provider': 'legacy-model', 'arm': 'wrapped',
            'passes': 1, 'graded': 1, 'n_tasks': 4,
            'unverifiable': 3, 'pass_rate': 1.0,
          }],
        },
      }), 200);
    }));
    await tester.pumpWidget(MaterialApp(theme: flywheelLightTheme(),
        home: Scaffold(body: UpliftView(client: client, alive: true))));
    await tester.pumpAndSettle();
    expect(find.text('DIAGNOSTIC ONLY'), findsOneWidget);
    expect(find.textContaining('confirmed 1/4'), findsOneWidget);
    expect(find.text('UPLIFT MEASURED'), findsNothing);
    expect(find.textContaining('95% [0.600'), findsNothing);
  });
}
