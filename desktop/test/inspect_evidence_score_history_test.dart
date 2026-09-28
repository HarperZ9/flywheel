import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/inspect_evidence_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/inspect_evidence_result_view.dart';

void main() {
  test('score edit history coverage and source pointers stay visible', () {
    final result = InspectImportResult.fromJson(_scoreHistoryBody());
    final report = result.report!;

    expect(report.semanticVerification, 'UNVERIFIABLE');
    expect(report.scoreHistory.label,
        'score history present 1 · empty 0 · missing 0');
    expect(
      report.rows
          .firstWhere(
              (row) => row.scorerName == 'match' && row.scoreValueText == 'I')
          .scoreHistoryLabel,
      'score history present (2 events)',
    );
    expect(_sourceValue(report, '/samples/0/scores/match/value'), 'I');
    expect(
        _sourceValue(report, '/samples/0/scores/match/history/0/value'), 'C');
    expect(
        _sourceValue(report, '/samples/0/scores/match/history/1/value'), 'I');
    expect(_sourceValue(report, '/samples/0/scores/match/history/1/reason'),
        'manual_review');
    expect(
      _sourceValue(
          report, '/samples/0/scores/match/history/1/provenance/author'),
      'flywheel-test',
    );
    expect(
      _sourceValue(
          report, '/samples/0/scores/match/history/1/provenance/reason'),
      'bounded edit provenance acceptance',
    );
  });

  test('missing score history is unknown, not no edits', () {
    final body = _scoreHistoryBody();
    final report = body['report'] as Map<String, Object?>;
    final coverage = report['scoring_coverage'] as Map<String, Object?>;
    coverage['score_history'] = {
      'present': 0,
      'empty': 0,
      'missing': 1,
    };
    final samples = report['samples'] as List<Object?>;
    final sample = samples.single as Map<String, Object?>;
    final scores = sample['scores'] as List<Object?>;
    final score = scores.single as Map<String, Object?>;
    score.remove('score_history');
    report['source_pointers'] = [
      {'json_pointer': '/samples/0/scores/match/value', 'source_value': 'I'},
    ];

    final parsed = InspectImportResult.fromJson(body).report!;

    expect(parsed.scoreHistory.label,
        'score history present 0 · empty 0 · missing 1');
    final scoreRow = parsed.rows.firstWhere(
        (row) => row.scorerName == 'match' && row.scoreValueText == 'I');
    final pointerRow = parsed.rows
        .firstWhere((row) => row.pointer == '/samples/0/scores/match/value');
    expect(scoreRow.scoreHistoryLabel, 'score history unknown');
    expect(pointerRow.sourceValueText, 'I');
  });

  testWidgets('score edit provenance reaches the Inspect native view',
      (tester) async {
    final result = InspectImportResult.fromJson(_scoreHistoryBody());

    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: InspectEvidenceResultView(result: result),
        ),
      ),
    ));

    expect(find.text('SEMANTIC UNVERIFIABLE'), findsOneWidget);
    expect(find.textContaining('SCORE HISTORY PRESENT 1'), findsOneWidget);
    expect(find.textContaining('score history present (2 events)'),
        findsOneWidget);
    expect(find.textContaining('/samples/0/scores/match/history/0/value'),
        findsOneWidget);
    expect(
        find.textContaining(
            '/samples/0/scores/match/history/1/provenance/author'),
        findsOneWidget);

    final authorPointer = find
        .textContaining('/samples/0/scores/match/history/1/provenance/author');
    await tester.ensureVisible(authorPointer);
    await tester.tap(authorPointer);
    await tester.pumpAndSettle();

    expect(find.textContaining('flywheel-test'), findsWidgets);
    expect(find.textContaining('bounded edit provenance acceptance'),
        findsWidgets);
    expect(find.textContaining('no edits'), findsNothing);
    expect(find.text('PASS'), findsNothing);
  });
}

Map<String, Object?> _scoreHistoryBody() {
  final report = jsonDecode(
    File('test/fixtures/native_inspect_score_history_report.json')
        .readAsStringSync(),
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
      'eid': 'eid-score-history',
      'sha256': _repeat('b', 64),
      'chain_hash': _repeat('c', 64),
    },
  };
}

String _sourceValue(InspectEvidenceReport report, String pointer) =>
    report.rows.firstWhere((row) => row.pointer == pointer).sourceValueText;

String _repeat(String value, int count) => List.filled(count, value).join();
