import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/inspect_evidence_models.dart';
import 'package:flywheel_desktop/services/inspect_file_picker.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/inspect_evidence_import_panel.dart';

const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding(_journey, _head);
const _unitContentType =
    'application/vnd.flywheel.inspect-import-with-unit-contract+json';

void main() {
  test('uploadInspectEvidence wraps scorer-unit sidecar in JSON envelope',
      () async {
    final sourceBytes = Uint8List.fromList(utf8.encode('{"ok":true}'));
    final unitBytes = Uint8List.fromList(utf8.encode('{"unit":true}'));
    late Map<String, Object?> envelope;
    final upload = InspectEvidenceUpload.fromBytes(
      sourceBytes,
      filename: 'run.json',
      clientRequestId: 'inspect-unit-client',
    ).withUnitContract(InspectUnitContractUpload.fromBytes(
      unitBytes,
      filename: 'run.unit.json',
    ));
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: AuthedClient(_InspectSpy((request) {
        expect(request.headers['Content-Type'], _unitContentType);
        expect(request.headers['X-Flywheel-Inspect-Sha256'], isNull);
        expect(
            request.headers['Content-Length'], '${request.bodyBytes.length}');
        envelope =
            jsonDecode(utf8.decode(request.bodyBytes)) as Map<String, Object?>;
        expect(envelope['schema'],
            'flywheel.inspect-import-with-unit-contract-request/v1');
        expect(envelope['filename'], 'run.json');
        expect(envelope['inspect_sha256'], upload.sha256);
        expect(envelope['inspect_byte_length'], sourceBytes.length);
        expect(base64Decode(envelope['inspect_json_base64']! as String),
            sourceBytes);
        expect(base64Decode(envelope['unit_contract_json_base64']! as String),
            unitBytes);
        return _successBody(upload.sha256);
      }), readToken: () => 'tok'),
    );

    final result = await client.uploadInspectEvidence(
      upload,
      binding: _binding,
      grantRef: _grant,
    );

    expect(result.errorCode, isNull);
    expect(envelope['inspect_byte_length'], sourceBytes.length);
  });

  testWidgets('Inspect panel selects optional scorer-unit sidecar',
      (tester) async {
    final sourceBytes = Uint8List.fromList(utf8.encode('{"ok":true}'));
    final unitBytes = Uint8List.fromList(utf8.encode('{"unit":true}'));
    final sourceSha = sha256.convert(sourceBytes).toString();
    var uploads = 0;
    Map<String, Object?>? envelope;
    final client = GatewayClient(
      baseUrl: 'https://gateway.invalid',
      httpClient: MockClient((request) async {
        if (request.method == 'GET' &&
            request.url.path == '/api/import/inspect') {
          return http.Response(jsonEncode(_emptyListBody()), 200);
        }
        uploads += 1;
        envelope = jsonDecode(request.body) as Map<String, Object?>;
        return http.Response(jsonEncode(_successBody(sourceSha)), 200);
      }),
    );

    await tester.pumpWidget(_wrap(_scope(
      child: InspectEvidenceImportPanel(
        client: client,
        picker: _FakePicker(sourceBytes, 'run.json'),
        unitContractPicker: _FakePicker(unitBytes, 'run.unit.json'),
      ),
    )));
    await tester.tap(find.text('Select Inspect JSON'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Select scorer unit sidecar'));
    await tester.pumpAndSettle();

    expect(find.textContaining('unit sidecar'), findsWidgets);
    expect(
        find.textContaining(
            sha256.convert(unitBytes).toString().substring(0, 24)),
        findsWidgets);

    await tester.tap(find.text('Request approval'));
    await tester.pumpAndSettle();

    expect(uploads, 1);
    expect(envelope?['schema'],
        'flywheel.inspect-import-with-unit-contract-request/v1');
    expect(find.textContaining('MAPPING CONSISTENCY MATCH'), findsOneWidget);
  });
}

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

GatewayOperationScope _scope({required Widget child}) => GatewayOperationScope(
      authorize: (context, operation, currentOperation, dispatch) async {
        expect(operation.action, 'import.inspect');
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
          'observed_samples': 1
        },
        'scoring_coverage': {'coverage_complete': true},
        'samples': const [],
        'source_pointers': const [],
        'scorer_unit_analysis': {
          'schema': 'flywheel.inspect-scorer-unit-analysis/v1',
          'semantic_verification': 'UNVERIFIABLE',
          'contracts': [
            {
              'scorer': 'match',
              'actual_score_unit': 'inspect_sample',
              'actual_score_cardinality': 1,
              'declared_intended_unit': 'python_test_function_definition',
              'declared_intended_cardinality': 1,
              'source_rows': 1,
              'scored_source_rows_for_named_scorer': 1,
              'covered_source_rows': 1,
              'excluded_source_rows': 0,
              'mapped_definitions': 1,
              'mapping_consistency': {
                'status': 'MATCH',
                'reason_codes': const []
              },
              'score_unit_relationship': {'status': 'many-to-one'},
              'definition_score_coverage': {'status': 'UNVERIFIABLE'},
              'source_item_mapping': [
                {
                  'source_row': {
                    'sample_index': 0,
                    'sample_id': 'one',
                    'sample_id_ref': {
                      'json_pointer': '/samples/0/id',
                      'source_value': 'one',
                    },
                    'epoch_ref': {
                      'json_pointer': '/samples/0/epoch',
                      'source_value': 1,
                    },
                    'score_ref': {
                      'json_pointer': '/samples/0/scores/match/value',
                      'source_value': 'I',
                    },
                  },
                  'mapped_definitions': {
                    'unit': 'python_test_function_definition',
                    'count': 1,
                    'refs': [
                      {
                        'unit_id': 'one',
                        'source': {
                          'container_pointer': '/samples/0/output/completion',
                          'container_value_sha256':
                              'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                          'span': {
                            'encoding': 'json-string-codepoints-v1',
                            'start': 0,
                            'end': 27,
                          },
                          'source_value': 'def test_one():\n  assert True',
                          'source_value_sha256':
                              'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
                        },
                      }
                    ],
                  },
                }
              ],
            }
          ],
          'does_not_prove': const [],
        },
      },
    };

Map<String, Object?> _emptyListBody() => {
      'schema': 'flywheel.inspect-import-list/v1',
      'items': const [],
    };

class _InspectSpy extends http.BaseClient {
  _InspectSpy(this.reply);
  final Map<String, Object?> Function(http.Request request) reply;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final typed = request as http.Request;
    return http.StreamedResponse(
      Stream.value(utf8.encode(jsonEncode(reply(typed)))),
      200,
      headers: {'content-type': 'application/json'},
    );
  }
}

final class _FakePicker implements InspectFilePicker {
  _FakePicker(this.bytes, this.filename);
  final Uint8List bytes;
  final String filename;

  @override
  Future<PickedInspectFile?> pick() async =>
      PickedInspectFile(bytes, filename: filename);
}
