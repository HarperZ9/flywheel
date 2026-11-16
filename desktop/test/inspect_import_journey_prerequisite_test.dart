import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/inspect_evidence_upload.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/inspect_file_picker.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/inspect_evidence_import_panel.dart';
import 'package:flywheel_desktop/widgets/operation_grant_sheet.dart';

import 'journey_controller_test.dart';

const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposal = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

void main() {
  testWidgets('missing Journey is a prerequisite failure, not denial',
      (tester) async {
    final journey = await _journeyWithoutProjection(const []);
    final operation = _upload().operation();
    var dispatched = false;
    GatewayAuthorizationOutcome<Object?>? outcome;
    final client = _client((request) async {
      fail('grant prepare must not run without a Journey');
    });
    final grants = GatewayOperationController(GatewayGrantClient(client));

    await tester.pumpWidget(_wrap(GatewayOperationScope(
      authorize: journeyGatewayAuthorizer(grants, journey.controller),
      child: Builder(builder: (context) {
        return FilledButton(
          onPressed: () async {
            outcome = await authorizeGatewayOperationDetailed<Object?>(
              context,
              operation,
              (_) async {
                dispatched = true;
                return Object();
              },
              currentOperation: () => operation,
            );
          },
          child: const Text('Authorize'),
        );
      }),
    )));

    await tester.tap(find.text('Authorize'));
    await tester.pumpAndSettle();

    expect(dispatched, isFalse);
    expect(outcome?.denied, isFalse);
    expect(outcome?.failure?.code, 'JOURNEY_REQUIRED');
  });

  testWidgets('fresh import requires explicit Journey selection before upload',
      (tester) async {
    final upload = _upload();
    final journey = await _journeyWithoutProjection([projection()]);
    final httpLog = <String>[];
    final client = _client((request) async {
      httpLog.add('${request.method} ${request.url.path}');
      if (_isInspectList(request)) return _emptyList();
      if (request.url.path.contains('/prepare/')) {
        fail('grant prepare must wait for explicit Journey selection');
      }
      fail('unexpected ${request.method} ${request.url.path}');
    });

    await _pumpImport(tester, client, journey.controller, upload);
    await tester.tap(find.text('Select Inspect JSON'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Select or create a Journey'), findsOneWidget);
    final requestButton = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Request approval'));
    expect(requestButton.onPressed, isNull);
    expect(httpLog.where((item) => item.contains('/prepare/')), isEmpty);

    journey.api.reply(resumeA, projection());
    await tester.tap(find.textContaining('Use Journey').first);
    await tester.pumpAndSettle();

    expect(journey.controller.state.projection?.journeyRef, journeyA);
    final enabled = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Request approval'));
    expect(enabled.onPressed, isNotNull);
  });

  testWidgets('selected Journey approval dispatches source-bound upload',
      (tester) async {
    final upload = _upload();
    final journey = await readyHarness(ScriptedJourneyApi());
    final seenBodies = <Map<String, Object?>>[];
    final uploadHeaders = <String, String>{};
    var uploads = 0;
    final client = _client((request) async {
      if (_isInspectList(request)) return _emptyList();
      if (request.method == 'POST' &&
          request.url.path == '/api/gateway-grants/prepare/import.inspect') {
        final body = jsonDecode(request.body) as Map<String, Object?>;
        seenBodies.add(body);
        return http.Response(jsonEncode(_grantProposal(body)), 200);
      }
      if (request.method == 'POST' &&
          request.url.path == '/api/gateway-grants/approve-once') {
        return http.Response(
            jsonEncode({
              'schema': 'flywheel.operation-grant-approval/v1',
              'grant_ref': _grant,
              'expires_at': '2026-08-15T12:00:00Z',
            }),
            200);
      }
      if (request.method == 'POST' &&
          request.url.path == '/api/import/inspect') {
        uploads += 1;
        uploadHeaders.addAll(request.headers);
        expect(request.bodyBytes, upload.bytes);
        return http.Response(jsonEncode(_successBody(upload.sha256)), 200);
      }
      fail('unexpected ${request.method} ${request.url.path}');
    });

    await _pumpImport(tester, client, journey.controller, upload);
    await tester.tap(find.text('Select Inspect JSON'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Request approval'));
    await tester.pumpAndSettle();

    expect(find.text('Approve one external operation'), findsOneWidget);
    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();

    expect(seenBodies.single['journey_ref'], journeyA);
    expect(seenBodies.single['expected_event_head'], headA);
    expect(uploadHeaders['X-Flywheel-Journey-Ref'], journeyA);
    expect(uploadHeaders['X-Flywheel-Expected-Event-Head'], headA);
    expect(uploadHeaders['X-Flywheel-Grant-Ref'], _grant);
    expect(uploads, 1);
    expect(find.textContaining('REPORTED SUCCESS'), findsWidgets);
  });
}

InspectEvidenceUpload _upload() {
  final bytes = Uint8List.fromList(utf8.encode('{"ok":true}'));
  return InspectEvidenceUpload.forTest(
    bytes: bytes,
    sha256: sha256.convert(bytes).toString(),
    byteLength: bytes.length,
    clientRequestId: 'inspect-request-1',
    filename: 'run.json',
  );
}

Future<ControllerHarness> _journeyWithoutProjection(
    List<JourneySummary> journeys) async {
  final api = ScriptedJourneyApi()..reply('list', journeys);
  final harness = ControllerHarness(api);
  addTearDown(harness.dispose);
  await harness.controller.initialize();
  return harness;
}

GatewayClient _client(Future<http.Response> Function(http.Request) handler) =>
    GatewayClient(
        baseUrl: 'https://gateway.invalid', httpClient: MockClient(handler));

Future<void> _pumpImport(WidgetTester tester, GatewayClient client,
    JourneyController journey, InspectEvidenceUpload upload) async {
  final grants = GatewayOperationController(GatewayGrantClient(client));
  await tester.pumpWidget(_wrap(GatewayOperationScope(
    authorize: journeyGatewayAuthorizer(grants, journey),
    child: InspectEvidenceImportPanel(
      client: client,
      journey: journey,
      picker: _Picker(upload),
    ),
  )));
  await tester.pumpAndSettle();
}

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

bool _isInspectList(http.Request request) =>
    request.method == 'GET' && request.url.path == '/api/import/inspect';

http.Response _emptyList() => http.Response(
      jsonEncode({
        'schema': 'flywheel.inspect-import-list/v1',
        'items': const [],
      }),
      200,
    );

Map<String, Object?> _grantProposal(Map<String, Object?> prepare) {
  final operation = prepare['operation'] as Map<String, Object?>;
  final source = operation['source'] as Map<String, Object?>;
  final sha = source['sha256']! as String;
  final dataRefs = operation['data_refs'] as List;
  return {
    'schema': 'flywheel.gateway-grant-proposal/v1',
    'proposal_ref': _proposal,
    'planned_grant_ref': _grant,
    'action': 'import.inspect',
    'journey_ref': prepare['journey_ref'],
    'expected_event_head': prepare['expected_event_head'],
    'client_request_id': prepare['client_request_id'],
    'destination': {
      'kind': 'import',
      'ref': 'inspect-json:${sha.substring(0, 16)}'
    },
    'tool': 'import.inspect',
    'operation_sha256': headA,
    'arguments_sha256': headA,
    'scopes': ['write'],
    'data_refs': List<String>.from(dataRefs),
    'credential_refs': const [],
    'expires_at': '2026-08-15T12:02:00Z',
    'summary': {
      'schema': 'flywheel.gateway-grant-summary/v1',
      'action': 'import.inspect',
      'journey_ref': prepare['journey_ref'],
      'expected_event_head': prepare['expected_event_head'],
      'destination': {
        'kind': 'import',
        'ref': 'inspect-json:${sha.substring(0, 16)}'
      },
      'tool': 'import.inspect',
      'operation_sha256': headA,
      'arguments_sha256': headA,
      'scopes': ['write'],
      'data_refs': List<String>.from(dataRefs),
      'credential_refs': const [],
      'effect': 'one dispatch after approval',
      'expires_at': '2026-08-15T12:02:00Z',
    },
  };
}

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
          'samples_with_scores': 0,
          'sample_score_records': 0,
          'result_scores': const [],
        },
        'samples': const [],
        'source_pointers': const [],
      },
      'stored': {
        'kind': 'inspect-evidence',
        'eid': 'eid-1',
        'sha256': List.filled(64, 'b').join(),
        'chain_hash': List.filled(64, 'c').join(),
      },
    };

final class _Picker implements InspectFilePicker {
  const _Picker(this.upload);
  final InspectEvidenceUpload upload;
  @override
  Future<PickedInspectFile?> pick() async =>
      PickedInspectFile(upload.bytes, filename: upload.filename);
}
