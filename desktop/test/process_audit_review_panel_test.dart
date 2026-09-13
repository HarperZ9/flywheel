import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/process_audit_review.dart';
import 'package:flywheel_desktop/services/inspect_file_picker.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/process_audit_review_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('reviews packet bytes and expands pointer value with location',
      (tester) async {
    final packet = Uint8List.fromList(utf8.encode(
      '{"schema":"flywheel.incident-sim-process-audit/v1",'
      '"source_values":{"target_state":"closed"}}',
    ));
    late List<int> sent;
    late Map<String, String> headers;
    final client = GatewayClient(
      httpClient: MockClient((request) async {
        sent = request.bodyBytes;
        headers = request.headers;
        final upload = ProcessAuditPacketUpload.fromPickedBytes(packet);
        return http.Response(
          jsonEncode(_body(upload.sha256, upload.byteLength)),
          200,
        );
      }),
    );

    await tester.pumpWidget(_wrap(ProcessAuditReviewPanel(
      client: client,
      picker: _Picker(packet, filename: 'packet.json'),
    )));
    await tester.tap(find.text('Select process-audit JSON'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review packet'));
    await tester.pumpAndSettle();

    expect(sent, packet);
    expect(headers['Content-Type'], 'application/json');
    expect(headers['X-Flywheel-Grant-Ref'], isNull);
    expect(find.text('PACKET INTEGRITY MATCH'), findsOneWidget);
    expect(find.text('SEMANTIC UNVERIFIABLE'), findsOneWidget);
    expect(find.textContaining('Declared access coverage not assessed'),
        findsOneWidget);
    expect(find.text('/source_values/target_state'), findsOneWidget);
    await tester.tap(find.text('/source_values/target_state'));
    await tester.pumpAndSettle();
    expect(find.text('closed'), findsWidgets);
    expect(find.textContaining('line 1'), findsWidgets);
    expect(find.textContaining('offset'), findsWidgets);
    expect(find.textContaining('semantic correctness'), findsOneWidget);
  });

  testWidgets('drift keeps reported coverage separate from declared coverage',
      (tester) async {
    final packet = Uint8List.fromList(utf8.encode(
      '{"schema":"flywheel.incident-sim-process-audit/v1",'
      '"source_values":{"target_state":"open"}}',
    ));
    final upload = ProcessAuditPacketUpload.fromPickedBytes(packet);
    final client = GatewayClient(
      httpClient: MockClient((_) async => http.Response(
            jsonEncode(_body(
              upload.sha256,
              upload.byteLength,
              assessment: 'packet-local-drift',
              declaredVerdict: 'DRIFT',
              coverage: 'unknown',
              reportedCoverage: 'complete',
            )),
            200,
          )),
    );

    await tester.pumpWidget(_wrap(ProcessAuditReviewPanel(
      client: client,
      picker: _Picker(packet),
    )));
    await tester.tap(find.text('Select process-audit JSON'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review packet'));
    await tester.pumpAndSettle();

    expect(find.text('PACKET INTEGRITY DRIFT'), findsOneWidget);
    expect(find.textContaining('Declared access coverage unknown'),
        findsOneWidget);
    expect(find.textContaining('Reported coverage complete'), findsOneWidget);
    expect(find.textContaining('reported coverage is untrusted'), findsOneWidget);
  });

  testWidgets('empty and malformed selections fail closed', (tester) async {
    final client = GatewayClient(
      httpClient: MockClient((_) async => http.Response(
            jsonEncode({
              'schema': 'flywheel.evidence-transport-error/v1',
              'error': {'code': 'INVALID_JSON', 'message': 'strict JSON only'},
            }),
            400,
          )),
    );

    await tester.pumpWidget(_wrap(ProcessAuditReviewPanel(
      client: client,
      picker: _Picker(Uint8List(0)),
    )));
    await tester.tap(find.text('Select process-audit JSON'));
    await tester.pumpAndSettle();
    expect(find.textContaining('INVALID_LENGTH'), findsOneWidget);

    await tester.pumpWidget(_wrap(ProcessAuditReviewPanel(
      key: UniqueKey(),
      client: client,
      picker: _Picker(Uint8List.fromList(utf8.encode('{'))),
    )));
    await tester.tap(find.text('Select process-audit JSON'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review packet'));
    await tester.pumpAndSettle();
    expect(find.textContaining('INVALID_JSON'), findsOneWidget);
    expect(find.text('PACKET INTEGRITY MATCH'), findsNothing);
  });
}

Map<String, Object?> _body(
  String sha,
  int byteLength, {
  String assessment = 'packet-local-match',
  String declaredVerdict = 'NOT_ASSESSED',
  String coverage = 'not_assessed',
  String? reportedCoverage,
}) =>
    {
      'schema': ProcessAuditReviewResult.schemaName,
      'source': {
        'format': 'incident-sim-process-audit-json',
        'sha256': sha,
        'byte_length': byteLength,
      },
      'assessment': assessment,
      'semantic_verification': 'UNVERIFIABLE',
      'verification': {
        'schema': 'flywheel.incident-sim-process-audit-verification/v1',
        'verdict': assessment.endsWith('match') ? 'MATCH' : 'DRIFT',
        'institutional_access_verdict': declaredVerdict,
        'packet_digest_verdict': assessment.endsWith('match') ? 'MATCH' : 'DRIFT',
        'evaluation_digest_verdict': 'MATCH',
        'source_values_digest_verdict': 'MATCH',
        'independence_digest_verdict': 'MATCH',
      },
      'declared_access': {
        'verdict': declaredVerdict,
        'coverage_assessment': coverage,
        if (reportedCoverage != null)
          'reported_coverage_assessment': reportedCoverage,
        'limits': [
          if (declaredVerdict == 'NOT_ASSESSED')
            'institutional_access component absent; declared access coverage was not assessed'
          else
            'reported coverage is untrusted',
        ],
      },
      'source_pointers': [
        {'json_pointer': '/source_values/target_state', 'source_value': 'closed'},
      ],
      'does_not_prove': ['semantic correctness or actual lab access'],
    };

class _Picker implements InspectFilePicker {
  const _Picker(this.bytes, {this.filename});
  final Uint8List bytes;
  final String? filename;

  @override
  Future<PickedInspectFile?> pick() async =>
      PickedInspectFile(bytes, filename: filename);
}
