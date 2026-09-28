import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/inspect_evidence_models.dart';

void main() {
  test('malformed score history coverage fails closed', () {
    final negativeCoverage = _scoreHistoryBody();
    _coverage(negativeCoverage)['score_history'] = {
      'present': -1,
      'empty': 0,
      'missing': 0,
    };
    _expectInvalidReport(negativeCoverage);

    final inconsistentCoverage = _scoreHistoryBody();
    _coverage(inconsistentCoverage)['score_history'] = {
      'present': 0,
      'empty': 0,
      'missing': 1,
    };
    _expectInvalidReport(inconsistentCoverage);

    final emptyCoverage = _scoreHistoryBody();
    _coverage(emptyCoverage)['score_history'] = <String, Object?>{};
    _expectInvalidReport(emptyCoverage);

    final nonObjectCoverage = _scoreHistoryBody();
    _coverage(nonObjectCoverage)['score_history'] = 'present:1';
    _expectInvalidReport(nonObjectCoverage);

    final nullCoverage = _scoreHistoryBody();
    _coverage(nullCoverage)['score_history'] = null;
    _expectInvalidReport(nullCoverage);
  });

  test('absent score history coverage remains legacy unknown', () {
    final body = _scoreHistoryBody();
    _coverage(body).remove('score_history');

    final parsed = InspectImportResult.fromJson(body).report!;

    expect(parsed.scoreHistory.label, 'score history unknown');
  });

  test('contradictory score history rows fail closed', () {
    final emptyWithEvents = _scoreHistoryBody();
    _score(emptyWithEvents)['score_history'] = {
      'state': 'empty',
      'events': [
        {'value': 'C'}
      ],
    };
    _expectInvalidReport(emptyWithEvents);

    final presentWithoutEvents = _scoreHistoryBody();
    _score(presentWithoutEvents)['score_history'] = {
      'state': 'present',
      'events': [],
    };
    _expectInvalidReport(presentWithoutEvents);

    final missingEvents = _scoreHistoryBody();
    _score(missingEvents)['score_history'] = {'state': 'present'};
    _expectInvalidReport(missingEvents);

    final malformedEvent = _scoreHistoryBody();
    _score(malformedEvent)['score_history'] = {
      'state': 'present',
      'events': [null],
    };
    _expectInvalidReport(malformedEvent);

    final emptyEvent = _scoreHistoryBody();
    _score(emptyEvent)['score_history'] = {
      'state': 'present',
      'events': [<String, Object?>{}],
    };
    _expectInvalidReport(emptyEvent);

    final malformedValue = _scoreHistoryBody();
    _score(malformedValue)['score_history'] = {
      'state': 'present',
      'events': [
        {'value': null}
      ],
    };
    _expectInvalidReport(malformedValue);

    final malformedValueItem = _scoreHistoryBody();
    _score(malformedValueItem)['score_history'] = {
      'state': 'present',
      'events': [
        {
          'value': [
            {'nested': 'not a score scalar'}
          ]
        }
      ],
    };
    _expectInvalidReport(malformedValueItem);

    final nonFiniteValue = _scoreHistoryBody();
    _score(nonFiniteValue)['score_history'] = {
      'state': 'present',
      'events': [
        {'value': double.infinity}
      ],
    };
    _expectInvalidReport(nonFiniteValue);

    final malformedReason = _scoreHistoryBody();
    _score(malformedReason)['score_history'] = {
      'state': 'present',
      'events': [
        {'reason': 7}
      ],
    };
    _expectInvalidReport(malformedReason);

    final malformedProvenance = _scoreHistoryBody();
    _score(malformedProvenance)['score_history'] = {
      'state': 'present',
      'events': [
        {'provenance': 7}
      ],
    };
    _expectInvalidReport(malformedProvenance);

    final malformedProvenanceField = _scoreHistoryBody();
    _score(malformedProvenanceField)['score_history'] = {
      'state': 'present',
      'events': [
        {
          'provenance': {'author': 7}
        }
      ],
    };
    _expectInvalidReport(malformedProvenanceField);

    final unsafeProvenanceField = _scoreHistoryBody();
    _score(unsafeProvenanceField)['score_history'] = {
      'state': 'present',
      'events': [
        {
          'provenance': {'metadata': 'not retained'}
        }
      ],
    };
    _expectInvalidReport(unsafeProvenanceField);

    final malformedRedactedFields = _scoreHistoryBody();
    _score(malformedRedactedFields)['score_history'] = {
      'state': 'present',
      'events': [
        {'redacted_fields': 'metadata'}
      ],
    };
    _expectInvalidReport(malformedRedactedFields);

    final malformedRedactedFieldItem = _scoreHistoryBody();
    _score(malformedRedactedFieldItem)['score_history'] = {
      'state': 'present',
      'events': [
        {
          'redacted_fields': [7]
        }
      ],
    };
    _expectInvalidReport(malformedRedactedFieldItem);
  });

  test('valid unchanged and redacted-only score history events are accepted',
      () {
    final unchanged = _scoreHistoryBody();
    _score(unchanged)['score_history'] = {
      'state': 'present',
      'events': [
        {
          'value': 'UNCHANGED',
          'reason': 'UNCHANGED',
          'provenance': {
            'timestamp': '2026-09-13T15:26:00Z',
            'author': 'flywheel-test',
            'reason': 'explanation edit',
          },
          'redacted_fields': ['answer', 'explanation', 'metadata'],
        }
      ],
    };

    final unchangedReport = InspectImportResult.fromJson(unchanged).report!;

    expect(
      unchangedReport.rows
          .firstWhere(
              (row) => row.scorerName == 'match' && row.scoreValueText == 'I')
          .scoreHistoryLabel,
      'score history present (1 events)',
    );

    final redactedOnly = _scoreHistoryBody();
    _score(redactedOnly)['score_history'] = {
      'state': 'present',
      'events': [
        {
          'redacted_fields': ['metadata'],
        }
      ],
    };

    final redactedReport = InspectImportResult.fromJson(redactedOnly).report!;

    expect(
      redactedReport.rows
          .firstWhere(
              (row) => row.scorerName == 'match' && row.scoreValueText == 'I')
          .scoreHistoryLabel,
      'score history present (1 events)',
    );
  });
}

Map<String, Object?> _coverage(Map<String, Object?> body) {
  final report = body['report'] as Map<String, Object?>;
  return report['scoring_coverage'] as Map<String, Object?>;
}

Map<String, Object?> _score(Map<String, Object?> body) {
  final report = body['report'] as Map<String, Object?>;
  final samples = report['samples'] as List<Object?>;
  final sample = samples.single as Map<String, Object?>;
  final scores = sample['scores'] as List<Object?>;
  return scores.single as Map<String, Object?>;
}

void _expectInvalidReport(Map<String, Object?> body) {
  final result = InspectImportResult.fromJson(body);
  expect(result.errorCode, 'INVALID_RESPONSE');
  expect(result.report, isNull);
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

String _repeat(String value, int count) => List.filled(count, value).join();
