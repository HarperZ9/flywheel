import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/services/inspect_file_picker.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/inspect_evidence_import_panel.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding(_journey, _head);
const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

void main() {
  testWidgets('approved import renders source values and saved receipt',
      (tester) async {
    final bytes = Uint8List.fromList(utf8.encode('{"ok":true}'));
    final sha = sha256.convert(bytes).toString();
    GatewayOperation? captured;
    var uploads = 0;
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/api/import/inspect') {
          return http.Response(jsonEncode(_emptyListBody()), 200);
        }
        uploads += 1;
        return http.Response(jsonEncode(_successBody(sha)), 200);
      }),
    );

    await tester.pumpWidget(_wrap(
      _scope(
        onOperation: (operation) => captured = operation,
        child: InspectEvidenceImportPanel(
          client: client,
          picker: _FakePicker(bytes, 'run.json'),
        ),
      ),
    ));
    await tester.tap(find.text('Select Inspect JSON'));
    await tester.pumpAndSettle();
    expect(find.textContaining(sha.substring(0, 24)), findsWidgets);

    await tester.tap(find.text('Request approval'));
    await tester.pumpAndSettle();

    expect(uploads, 1);
    expect(captured?.action, 'import.inspect');
    expect(captured?.dataRefs, ['data_inspect.source:${sha.substring(0, 32)}']);
    expect((captured?.operation['source'] as Map)['byte_length'], bytes.length);
    expect(find.text('SEMANTIC UNVERIFIABLE'), findsOneWidget);
    expect(find.textContaining('REPORTED SUCCESS'), findsWidgets);
    expect(find.textContaining('ASSESSMENT REPORTED'), findsOneWidget);
    expect(find.textContaining('COVERAGE COMPLETE'), findsOneWidget);
    expect(find.textContaining('SAMPLES 1/1'), findsOneWidget);
    expect(find.textContaining('accuracy'), findsWidgets);
    expect(find.textContaining('0.75'), findsWidgets);
    final accuracyPointer =
        find.textContaining('/samples/0/scores/accuracy/value');
    await tester.ensureVisible(accuracyPointer);
    await tester.tap(accuracyPointer);
    await tester.pumpAndSettle();
    expect(find.textContaining('0.75'), findsWidgets);
    expect(find.textContaining('eid-1'), findsOneWidget);
    expect(find.text('PASS'), findsNothing);
  });

  testWidgets('denied grant does not upload bytes', (tester) async {
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/api/import/inspect') {
          return http.Response(jsonEncode(_emptyListBody()), 200);
        }
        fail('upload must not run');
      }),
    );
    await tester.pumpWidget(_wrap(
      _scope(
        denied: true,
        child: InspectEvidenceImportPanel(
          client: client,
          picker: _FakePicker(
            Uint8List.fromList(utf8.encode('{"ok":true}')),
            'run.json',
          ),
        ),
      ),
    ));

    await tester.tap(find.text('Select Inspect JSON'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Request approval'));
    await tester.pumpAndSettle();

    expect(find.textContaining('APPROVAL_DENIED'), findsOneWidget);
  });

  testWidgets('saved imports reopen after panel recreate', (tester) async {
    final body = _realImportBody();
    final source = body['source'] as Map<String, Object?>;
    final sha = source['sha256']! as String;
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/api/import/inspect') {
          return http.Response(
              jsonEncode(_listBody(sha, byteLength: 510)), 200);
        }
        if (request.method == 'GET' &&
            request.url.path == '/api/import/inspect/eid-1') {
          return http.Response(jsonEncode(body), 200);
        }
        return http.Response(
            'unexpected ${request.method} ${request.url}', 500);
      }),
    );

    await tester.pumpWidget(_wrap(InspectEvidenceImportPanel(client: client)));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(_wrap(InspectEvidenceImportPanel(client: client)));
    await tester.pumpAndSettle();

    expect(find.text('RECENT INSPECT IMPORTS'), findsOneWidget);
    expect(find.textContaining('eid-1'), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, 'Open').first);
    await tester.pumpAndSettle();

    expect(find.text('SEMANTIC UNVERIFIABLE'), findsOneWidget);
    expect(find.textContaining('REPORTED SUCCESS'), findsWidgets);
    expect(find.textContaining('ASSESSMENT INCOMPLETE'), findsOneWidget);
    expect(find.textContaining('COVERAGE INCOMPLETE'), findsOneWidget);
    expect(find.textContaining('SAMPLES 4/4'), findsOneWidget);
    expect(find.textContaining('INVALIDATED TRUE'), findsOneWidget);
    final matchPointer = find.textContaining('/samples/0/scores/match/value');
    expect(matchPointer, findsOneWidget);
    await tester.ensureVisible(matchPointer);
    await tester.tap(matchPointer);
    await tester.pumpAndSettle();
    expect(find.textContaining('C'), findsWidgets);
    expect(find.textContaining('eid-1'), findsWidgets);
    expect(find.text('PASS'), findsNothing);
  });

  testWidgets('saved import read failures never render semantic pass',
      (tester) async {
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/import/inspect') {
          return http.Response(jsonEncode(_listBody(_repeat('a', 64))), 200);
        }
        return http.Response(
          jsonEncode({
            'schema': 'flywheel.evidence-transport-error/v1',
            'error': {
              'code': 'STORE_TAMPERED',
              'message': 'Saved Inspect evidence failed integrity checks',
            },
          }),
          409,
        );
      }),
    );

    await tester.pumpWidget(_wrap(InspectEvidenceImportPanel(client: client)));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Open').first);
    await tester.pumpAndSettle();

    expect(find.textContaining('STORE_TAMPERED'), findsOneWidget);
    expect(find.text('PASS'), findsNothing);
  });
}

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

GatewayOperationScope _scope({
  required Widget child,
  bool denied = false,
  void Function(GatewayOperation operation)? onOperation,
}) =>
    GatewayOperationScope(
      authorize: (context, operation, currentOperation, dispatch) async {
        onOperation?.call(operation);
        if (denied) return const GatewayAuthorizationOutcome.denied();
        expect(currentOperation(), operation);
        final result = await dispatch(operation.finalBody(_binding, _grant));
        return GatewayAuthorizationOutcome.value(result);
      },
      child: child,
    );

Map<String, Object?> _successBody(String sha) => {
      'schema': 'flywheel.inspect-import-result/v1',
      'source': {'format': 'inspect-json', 'sha256': sha, 'byte_length': 11},
      'data_ref': 'data_inspect.source:${sha.substring(0, 32)}',
      'report': {
        'schema': 'flywheel.inspect-evidence/v1',
        'source': {'sha256': sha, 'byte_length': 11},
        'producer': {'format': 'inspect-json', 'version': 2},
        'reported_status': 'success',
        'assessment': 'reported',
        'invalidated': false,
        'semantic_verification': 'UNVERIFIABLE',
        'counts': {
          'total_samples': 1,
          'completed_samples': 1,
          'observed_samples': 1,
        },
        'scoring_coverage': {
          'coverage_complete': true,
          'samples_with_scores': 1,
          'sample_score_records': 1,
          'result_scores': [
            {
              'name': 'accuracy',
              'scorer': 'accuracy',
              'scored_samples': 1,
              'unscored_samples': 0,
            }
          ],
        },
        'samples': [
          {
            'id': 'case-1',
            'epoch': 1,
            'status': null,
            'error': null,
            'scores': [
              {'scorer': 'accuracy', 'value': 0.75}
            ],
          }
        ],
        'source_pointers': [
          {'json_pointer': '/status', 'source_value': 'success'},
          {
            'json_pointer': '/samples/0/scores/accuracy/value',
            'source_value': 0.75,
          }
        ],
      },
      'stored': {
        'kind': 'inspect-evidence',
        'eid': 'eid-1',
        'sha256': _repeat('b', 64),
        'chain_hash': _repeat('c', 64),
      },
    };

Map<String, Object?> _realImportBody() {
  final report = jsonDecode(
    File('test/fixtures/native_inspect_real_report.json').readAsStringSync(),
  ) as Map<String, Object?>;
  final source = report['source'] as Map<String, Object?>;
  final sha = source['sha256']! as String;
  return {
    'schema': 'flywheel.inspect-import-result/v1',
    'source': {...source, 'format': 'inspect-json'},
    'data_ref': 'data_inspect.source:${sha.substring(0, 32)}',
    'report': report,
    'stored': {
      'kind': 'inspect-evidence',
      'eid': 'eid-1',
      'sha256': _repeat('b', 64),
      'chain_hash': _repeat('c', 64),
    },
  };
}

Map<String, Object?> _listBody(String sha, {int byteLength = 11}) => {
      'schema': 'flywheel.inspect-import-list/v1',
      'items': [
        {
          'eid': 'eid-1',
          'source': {'sha256': sha, 'byte_length': byteLength},
          'reported_status': 'success',
          'stored': {'sha256': _repeat('b', 64)},
        }
      ],
    };

Map<String, Object?> _emptyListBody() => {
      'schema': 'flywheel.inspect-import-list/v1',
      'items': const [],
    };

String _repeat(String value, int count) => List.filled(count, value).join();

final class _FakePicker implements InspectFilePicker {
  _FakePicker(this.bytes, this.filename);

  final Uint8List bytes;
  final String filename;

  @override
  Future<PickedInspectFile?> pick() async =>
      PickedInspectFile(bytes, filename: filename);
}
