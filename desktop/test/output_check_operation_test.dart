import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/operation_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/output_check_panel.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _operation = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

void main() {
  test('output check operation result parses and rejects mismatched actions',
      () {
    final body = {
      'schema': 'flywheel.gateway-operation-result/v1',
      'operation_ref': _operation,
      'action': 'output.check',
      'state': 'completed',
      'result': {
        'verdict': 'UNVERIFIABLE',
        'release': 'HOLD',
        'cli_exit_code': 3,
      },
    };
    expect(OperationResult.fromJson(body).action, 'output.check');
    expect(
      () => OperationResult.fromJson({...body, 'action': 'suite.audit'}),
      throwsA(isA<ArgumentError>()),
    );
  });

  testWidgets('panel dispatches output.check through the typed operation path',
      (tester) async {
    GatewayOperation? captured;
    final result = {
      'schema': 'flywheel.gateway-operation-result/v1',
      'operation_ref': _operation,
      'action': 'output.check',
      'state': 'completed',
      'result': {
        'verdict': 'PASS',
        'release': 'RELEASE',
        'cli_exit_code': 0,
        'fields': <Object>[],
      },
    };
    final digest = OperationResult.fromJson(result).canonicalSha256;
    final terminal = {
      'schema': 'flywheel.gateway-operation-snapshot/v1',
      'operation_ref': _operation,
      'journey_ref': _journey,
      'event_head_sha256': _head,
      'state': 'completed',
      'can_cancel': false,
      'terminal_event_ref': _head,
      'result_sha256': digest,
    };
    late Uri seen;
    final client = GatewayClient(
      baseUrl: 'http://gateway.test',
      httpClient: MockClient((request) async {
        seen = request.url;
        final wire = 'id: 1\r\nevent: terminal\r\ndata: ${jsonEncode({
              'snapshot': terminal,
              'result': result,
            })}\r\n\r\n'
            'id: 2\r\nevent: terminal\r\ndata: [DONE]\r\n\r\n';
        return http.Response(wire, 200);
      }),
    );
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: (context, operation, currentOperation, dispatch) {
          captured = operation;
          return dispatch(operation.finalBody(
            const GatewayJourneyBinding(_journey, _head),
            'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          ));
        },
        child: Scaffold(body: OutputCheckPanel(client: client)),
      ),
    ));
    await tester.enterText(
      find.byKey(const ValueKey('output-check-contract-path')),
      'examples/output-validation/form-1040.contract.json',
    );
    await tester.enterText(
      find.byKey(const ValueKey('output-check-contract-sha')),
      'a' * 64,
    );
    await tester.enterText(
      find.byKey(const ValueKey('output-check-answer-path')),
      'examples/output-validation/answer-from-the-table.json',
    );
    await tester.enterText(
      find.byKey(const ValueKey('output-check-answer-sha')),
      'b' * 64,
    );
    await tester.tap(find.byKey(const ValueKey('output-check-allow-commands')));
    await tester.tap(find.text('Check output'));
    await tester.runAsync(
      () async => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pumpAndSettle();

    expect(seen.path, '/api/output/check');
    expect(captured?.action, 'output.check');
    expect(captured?.scopes, ['exec']);
    expect(find.text('PASS'), findsOneWidget);
    client.close();
  });
}
