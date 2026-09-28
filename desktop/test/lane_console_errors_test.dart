// lane_console_errors_test.dart - each fixed lane error code gets one
// sentence from its closed fields and one action (WP9b, PLAN section 2). The
// engine's fixed message is never shown; tool and stderr text never arrive.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/lane_console_fixture.dart';

void main() => _errorCases();

void _errorCases() {
  const cases = <String, (int, Map<String, Object>, String, String)>{
    'CAPABILITY_NOT_ADMITTED': (
      400,
      {
        'admitted': ['crucible.status']
      },
      'This build does not admit crucible.status. Admitted: crucible.status.',
      'List tools again'
    ),
    'NOT_IN_BUILD': (
      400,
      {'reason': 'numpy_not_in_build'},
      'Not in this build: crucible.status (numpy_not_in_build).',
      'List tools again'
    ),
    'LANE_SETUP_REQUIRED': (
      409,
      {
        'reason': 'node_missing',
        'setup': ['node']
      },
      'crucible needs a setup step first: Node.js 20 or later.',
      'Show setup'
    ),
    'LANE_CANNOT_LAUNCH': (
      503,
      {'reason': 'server_exited'},
      'Could not start: server_exited.',
      'Check the lane'
    ),
    'LANE_TIMEOUT': (
      504,
      {'reason': 'no_response', 'timeout_s': 20},
      'crucible.status did not answer within 20 s.',
      'Run again'
    ),
    'LANE_TOOL_ERROR': (
      502,
      {'reason': 'mcp_error'},
      'crucible.status reported an error (mcp_error). The tool text is not '
          'shown.',
      'Run again'
    ),
  };
  for (final entry in cases.entries) {
    testWidgets('${entry.key} gets its sentence and one action',
        (tester) async {
      final (status, extra, sentence, action) = entry.value;
      final checked = <String>[];
      final engine = LaneConsoleEngine()
        ..callStatus = status
        ..callBody = {
          'code': entry.key,
          'error': 'fixed message',
          'name': 'crucible',
          'tool': 'crucible.status',
          ...extra,
        };
      await pumpConsole(tester, engine,
          lane: consoleLane(setup: [
            {
              'id': 'node',
              'met': false,
              'title': 'Node.js 20 or later',
              'copy': 'Install Node.js 20 or later, or choose node.exe.'
            }
          ]),
          onCheck: checked.add);
      await listTools(tester);
      await chooseTool(tester, 'crucible.status');
      await tester.tap(find.text('Run'));
      await tester.pumpAndSettle();
      expect(find.text(sentence), findsOneWidget);
      expect(find.text('fixed message'), findsNothing);
      expect(find.widgetWithText(OutlinedButton, action), findsOneWidget);
      if (entry.key == 'LANE_CANNOT_LAUNCH') {
        await tester.tap(find.widgetWithText(OutlinedButton, action));
        expect(checked, ['crucible']);
      }
    });
  }
}
