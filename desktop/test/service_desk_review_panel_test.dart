import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/service_desk_review_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets(
    'requests a run-root relative ref and renders claimed vs recomputed',
    (tester) async {
      final seen = <String, dynamic>{};
      final client = GatewayClient(
        httpClient: MockClient((request) async {
          seen['method'] = request.method;
          seen['path'] = request.url.path;
          seen['body'] = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(_routeBody('pass')), 200);
        }),
      );

      await tester.pumpWidget(_wrap(ServiceDeskReviewPanel(client: client)));
      await tester.enterText(
        find.byType(TextField),
        'runs/service-desk-incident-v1-a',
      );
      await tester.tap(find.text('Review evidence'));
      await tester.pumpAndSettle();

      expect(seen['method'], 'POST');
      expect(seen['path'], '/api/enterprise-envs/service-desk-incident/review');
      expect(seen['body'], {
        'artifact_dir_ref': 'runs/service-desk-incident-v1-a',
      });
      expect(find.text('CLAIMED OUTCOME'), findsOneWidget);
      expect(find.text('RECOMPUTED OUTCOME'), findsOneWidget);
      expect(find.textContaining('recorded case flags passed'), findsOneWidget);
      expect(find.textContaining('recomputed pass'), findsOneWidget);
      expect(find.text('EXTERNAL TRUST NOT ESTABLISHED'), findsWidgets);
      expect(
        find.textContaining('Recorded case flags are not rerun'),
        findsOneWidget,
      );
      expect(find.textContaining('C:/'), findsNothing);
    },
  );

  testWidgets('semantic false success stays failed with explicit controls', (
    tester,
  ) async {
    final client = GatewayClient(
      httpClient: MockClient(
        (_) async => http.Response(jsonEncode(_routeBody('fail')), 200),
      ),
    );

    await tester.pumpWidget(_wrap(ServiceDeskReviewPanel(client: client)));
    await tester.enterText(find.byType(TextField), 'runs/false-success');
    await tester.tap(find.text('Review evidence'));
    await tester.pumpAndSettle();

    expect(find.text('FAIL'), findsWidgets);
    expect(find.textContaining('TARGET_INCIDENT_NOT_OPEN'), findsWidgets);
    expect(find.text('SOURCE INTEGRITY PASS'), findsOneWidget);
    expect(find.text('SYNTHETIC TASK FAIL'), findsOneWidget);
    expect(find.textContaining('fabricated complete outcome'), findsOneWidget);
  });

  testWidgets(
    'product upgrade errors are actionable and never rendered as pass',
    (tester) async {
      final client = GatewayClient(
        httpClient: MockClient(
          (_) async => http.Response(
            jsonEncode({
              'schema': 'flywheel.evidence-transport-error/v1',
              'error': {
                'code': 'PRODUCT_UPGRADE_REQUIRED',
                'message':
                    'install a ServiceDesk product with review_artifacts',
              },
            }),
            503,
          ),
        ),
      );

      await tester.pumpWidget(_wrap(ServiceDeskReviewPanel(client: client)));
      await tester.enterText(find.byType(TextField), 'runs/old-product');
      await tester.tap(find.text('Review evidence'));
      await tester.pumpAndSettle();

      expect(find.textContaining('PRODUCT_UPGRADE_REQUIRED'), findsOneWidget);
      expect(
        find.textContaining('install a ServiceDesk product'),
        findsOneWidget,
      );
      expect(find.text('PASS'), findsNothing);
    },
  );
}

Map<String, Object?> _routeBody(String observedState) => {
      'schema': 'flywheel.enterprise-env-review/v1',
      'environment_id': 'service-desk-incident/v1',
      'artifact_dir_ref': 'runs/service-desk-incident-v1-a',
      'artifact_label': 'service-desk-incident-v1-a',
      'report': {
        'schema': 'service-desk-incident-env-review/v1',
        'artifact_label': 'service-desk-incident-v1-a',
        'artifact_dir_ref': 'runs/service-desk-incident-v1-a',
        'verification': {
          'schema': 'service-desk-incident-env-artifact-verification/v1',
          'artifact_dir_ref': 'runs/service-desk-incident-v1-a',
          'observed_state': observedState,
          'failure_codes': observedState == 'pass'
              ? <String>[]
              : ['target_incident_not_open'],
        },
        'claimed_outcome': {
          'all_recorded_cases_passed': true,
          'recorded_case_count': 1,
          'basis':
              'receipt-recorded case flags; not accepted as semantic truth',
        },
        'recomputed_outcome': {
          'observed_state': observedState,
          'failure_codes': observedState == 'pass'
              ? <String>[]
              : ['target_incident_not_open'],
          'basis':
              'source_integrity, synthetic_task_check, and record_consistency',
        },
        'evidence_layers': {
          'source_integrity': {
            'observed_state': 'pass',
            'failure_codes': <String>[],
          },
          'synthetic_task_check': {
            'observed_state': observedState,
            'failure_codes': observedState == 'pass'
                ? <String>[]
                : ['target_incident_not_open'],
            'authorization': 'unchecked',
            'log_origin': 'submitted_untrusted',
          },
          'record_consistency': {
            'observed_state': 'pass',
            'failure_codes': <String>[],
          },
          'externally_trusted_evidence': {
            'observed_state': 'not_established',
            'reason':
                'No external signature, trusted timestamp, or independent evidence anchor is present in this bundle.',
          },
        },
        'limits': [
          'Recorded case flags are not rerun by this review.',
          'A fabricated complete outcome with matching fabricated logs could satisfy the synthetic task check.',
        ],
      },
    };
