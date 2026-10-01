import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_handoff.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_handoff_button.dart';

const _op = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _brief = '# Handoff: write notes\n\n- Final answer: claimed (no check)\n';

HandoffApi _api(List<String> seen, {int status = 200, Object? body}) =>
    HandoffApi(
        baseUrl: 'https://rowan.invalid',
        httpClient: MockClient((request) async {
          seen.add('${request.method} ${request.url.path}');
          return http.Response(
              jsonEncode(body ??
                  {
                    'schema': rowanHandoffSchema,
                    'operation_ref': _op,
                    'record_count': 7,
                    'trace_head_sha256': 'b' * 64,
                    'markdown': _brief,
                  }),
              status);
        }));

void main() {
  test('the brief is read from the engine and checked against its operation',
      () async {
    final seen = <String>[];
    final brief = await _api(seen).read(_op);
    expect(seen, ['GET /api/operations/$_op/handoff']);
    expect(brief.markdown, _brief);
    final wrongOperation = _api([], body: {
      'schema': rowanHandoffSchema,
      'operation_ref': 'op_${'c' * 32}',
      'record_count': 7,
      'trace_head_sha256': 'b' * 64,
      'markdown': _brief,
    });
    expect(() => wrongOperation.read(_op), throwsFormatException);
    expect(() => _api([]).read('op_bad'), throwsArgumentError);
  });

  testWidgets('the button copies the brief and says it was not re-checked',
      (tester) async {
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        copied = (call.arguments as Map)['text'] as String;
      }
      return null;
    });
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: RowanHandoffButton(
                baseUrl: 'https://rowan.invalid',
                operationRef: _op,
                api: _api([])))));
    await tester.tap(find.byKey(const Key('rowan-copy-handoff')));
    await tester.pumpAndSettle();
    expect(copied, _brief);
    expect(find.textContaining('Not re-checked at export'), findsOneWidget);
  });

  testWidgets('a refused brief is shown as an honest null', (tester) async {
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: RowanHandoffButton(
                baseUrl: 'https://rowan.invalid',
                operationRef: _op,
                api: _api([], status: 404, body: {
                  'error': {'code': 'NOT_FOUND', 'message': 'not found'}
                })))));
    await tester.tap(find.byKey(const Key('rowan-copy-handoff')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Handoff brief unavailable'), findsOneWidget);
  });
}
