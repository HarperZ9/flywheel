import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/inspect_evidence_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/inspect_evidence_result_view.dart';

const _sourceSha =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _storedSha =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _chainSha =
    'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';
const _spanHash =
    'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd';
const _containerHash =
    'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee';

void main() {
  testWidgets('scorer unit review separates row scores from mapped definitions',
      (tester) async {
    final result = InspectImportResult.fromJson(
      _resultBody(unit: _unitVerification(mappedDefinitions: 556)),
    );

    await tester.pumpWidget(_wrap(InspectEvidenceResultView(result: result)));

    expect(find.textContaining('MAPPING CONSISTENCY MATCH'), findsOneWidget);
    expect(find.textContaining('MEASUREMENT UNIT MATCH'), findsNothing);
    expect(find.textContaining('ACTUAL SCORED ROWS'), findsOneWidget);
    expect(find.textContaining('10 inspect samples'), findsOneWidget);
    expect(find.textContaining('/results/scores/0/scored_samples = 10'),
        findsOneWidget);
    expect(find.textContaining('MAPPED DEFINITIONS'), findsOneWidget);
    expect(find.textContaining('556 python test function definitions'),
        findsOneWidget);
    expect(find.textContaining('SCORE UNIT MANY TO ONE'), findsWidgets);
    expect(find.textContaining('DEFINITION SCORE COVERAGE UNVERIFIABLE'),
        findsWidgets);
    expect(find.textContaining('556 scored definitions'), findsNothing);
  });

  test(
      'unit verification parser accepts absent block and rejects malformed present block',
      () {
    final legacy = _resultBody();
    (legacy['report'] as Map<String, Object?>).remove('scorer_unit_analysis');
    final parsedLegacy = InspectImportResult.fromJson(legacy);
    expect(parsedLegacy.errorCode, isNull);
    expect(parsedLegacy.report?.measurementUnit, isNull);

    final malformed = _resultBody();
    (malformed['report'] as Map<String, Object?>)['scorer_unit_analysis'] = {
      'schema': 'flywheel.inspect-scorer-unit-analysis/v1',
      'semantic_verification': 'UNVERIFIABLE',
      'reason_codes': 'no_unit_contract',
      'contracts': const [],
      'does_not_prove': const [],
    };
    final parsedMalformed = InspectImportResult.fromJson(malformed);
    expect(parsedMalformed.errorCode, 'INVALID_RESPONSE');
  });

  test('unit parser accepts backend mapping with source metadata', () {
    final parsed = InspectImportResult.fromJson(_resultBody());
    final unit = parsed.report?.measurementUnit;
    expect(parsed.errorCode, isNull);
    expect(unit?.contracts.single.spanRefs.single.containerPointer,
        '/samples/0/output/completion');
    expect(unit?.contracts.single.spanRefs.single.sourceValue,
        contains('def test_unicode_😀'));
  });

  test('unit parser rejects missing mapping for mapped definitions', () {
    _expectUnitInvalid((contract) => contract.remove('source_item_mapping'));
  });

  test('unit parser rejects malformed mapping row', () {
    _expectUnitInvalid((contract) {
      contract['source_item_mapping'] = ['not a row'];
    });
  });

  test('unit parser rejects missing mapped definition refs', () {
    _expectUnitInvalid((contract) {
      final mapping = contract['source_item_mapping'] as List<Object?>;
      final row = mapping.single as Map<String, Object?>;
      final definitions = row['mapped_definitions'] as Map<String, Object?>;
      definitions.remove('refs');
    });
  });

  test('unit parser rejects missing source row refs', () {
    _expectUnitInvalid((contract) {
      final mapping = contract['source_item_mapping'] as List<Object?>;
      final row = mapping.single as Map<String, Object?>;
      final sourceRow = row['source_row'] as Map<String, Object?>;
      sourceRow.remove('score_ref');
    });
  });

  test('unit parser rejects mismatched mapped definition counts', () {
    _expectUnitInvalid((contract) {
      final mapping = contract['source_item_mapping'] as List<Object?>;
      final row = mapping.single as Map<String, Object?>;
      final definitions = row['mapped_definitions'] as Map<String, Object?>;
      definitions['count'] = 2;
    });
  });

  testWidgets('scorer unit span context is hidden until explicit source action',
      (tester) async {
    final result = InspectImportResult.fromJson(_resultBody());

    await tester.pumpWidget(_wrap(InspectEvidenceResultView(result: result)));

    expect(find.textContaining('def test_unicode_😀'), findsNothing);
    final pointer = find.textContaining('/samples/0/output/completion');
    expect(pointer, findsOneWidget);
    expect(find.textContaining('code point span 1..44'), findsOneWidget);
    expect(find.textContaining('PRIVATE SOURCE CONTEXT'), findsNothing);

    await tester.ensureVisible(find.text('Show private source context'));
    await tester.tap(find.text('Show private source context'));
    await tester.pumpAndSettle();

    expect(find.textContaining('PRIVATE SOURCE CONTEXT'), findsOneWidget);
    expect(find.textContaining('def test_unicode_😀'), findsOneWidget);
  });
}

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void _expectUnitInvalid(void Function(Map<String, Object?> contract) mutate) {
  final body = _resultBody();
  final report = body['report'] as Map<String, Object?>;
  final unit = report['scorer_unit_analysis'] as Map<String, Object?>;
  final contracts = unit['contracts'] as List<Object?>;
  mutate(contracts.single as Map<String, Object?>);
  expect(InspectImportResult.fromJson(body).errorCode, 'INVALID_RESPONSE');
}

Map<String, Object?> _resultBody({Map<String, Object?>? unit}) => {
      'schema': 'flywheel.inspect-import-result/v1',
      'source': {
        'format': 'inspect-json',
        'sha256': _sourceSha,
        'byte_length': 11,
      },
      'data_ref': 'data_inspect.source:${_sourceSha.substring(0, 32)}',
      'report': {
        'schema': 'flywheel.inspect-evidence/v1',
        'source': {'sha256': _sourceSha, 'byte_length': 11},
        'producer': {'format': 'inspect-json', 'version': 2},
        'reported_status': 'success',
        'assessment': 'reported',
        'invalidated': false,
        'semantic_verification': 'UNVERIFIABLE',
        'counts': {
          'total_samples': 10,
          'completed_samples': 10,
          'observed_samples': 10,
        },
        'scoring_coverage': {'coverage_complete': true},
        'samples': const [],
        'source_pointers': const [],
        'scorer_unit_analysis': unit ?? _unitVerification(),
      },
      'stored': {
        'kind': 'inspect-evidence',
        'eid': 'eid-unit',
        'sha256': _storedSha,
        'chain_hash': _chainSha,
      },
    };

Map<String, Object?> _unitVerification({int mappedDefinitions = 1}) => {
      'schema': 'flywheel.inspect-scorer-unit-analysis/v1',
      'semantic_verification': 'UNVERIFIABLE',
      'source_pointers': [
        {
          'json_pointer': '/results/scores/0/scored_samples',
          'source_value': 10
        },
      ],
      'contracts': [
        {
          'scorer': 'taxonomy',
          'source_rows': 10,
          'scored_source_rows_for_named_scorer': 10,
          'covered_source_rows': 10,
          'excluded_source_rows': 0,
          'mapped_definitions': mappedDefinitions,
          'actual_score_unit': 'inspect_sample',
          'actual_score_cardinality': 10,
          'declared_intended_unit': 'python_test_function_definition',
          'declared_intended_cardinality': mappedDefinitions,
          'mapping_consistency': {'status': 'MATCH', 'reason_codes': const []},
          'score_unit_relationship': {
            'status': 'many-to-one',
            'actual_score_unit': 'inspect_sample',
            'mapped_unit': 'python_test_function_definition',
            'actual_scored_units': 10,
            'mapped_units': mappedDefinitions,
          },
          'definition_score_coverage': {
            'status': 'UNVERIFIABLE',
            'reason_codes': ['no_per_definition_score_evidence'],
            'scored_definitions': null,
          },
          'identity_status': 'UNVERIFIABLE',
          'aggregation': 'many_to_one',
          'source_item_mapping': [
            {
              'source_row': {
                'sample_index': 0,
                'sample_id': 'batch-0',
                'sample_id_ref': {
                  'json_pointer': '/samples/0/id',
                  'source_value': 'batch-0',
                },
                'epoch_ref': {
                  'json_pointer': '/samples/0/epoch',
                  'source_value': 1,
                },
                'score_ref': {
                  'json_pointer': '/samples/0/scores/taxonomy/value',
                  'source_value': 'C',
                },
              },
              'mapped_definitions': {
                'unit': 'python_test_function_definition',
                'count': mappedDefinitions,
                'refs': _spanRefs(mappedDefinitions),
              },
            },
          ],
        }
      ],
      'does_not_prove': [
        'Mapping consistency does not prove scorer correctness.',
        'A many-to-one row score does not establish per-definition score coverage.',
      ],
    };

List<Map<String, Object?>> _spanRefs(int count) => [
      for (var index = 0; index < count; index++)
        {
          'unit_id': 'unicode_$index',
          'source': {
            'container_pointer': '/samples/0/output/completion',
            'container_value_sha256': _containerHash,
            'span': {
              'encoding': 'json-string-codepoints-v1',
              'start': 1,
              'end': 44,
            },
            'source_value': 'def test_unicode_😀():\n  assert "β"\n',
            'source_value_sha256': _spanHash,
          },
        },
    ];
