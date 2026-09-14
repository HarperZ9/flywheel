part of 'inspect_evidence_models.dart';

const _unitStatuses = {
  'MATCH',
  'PARTIAL',
  'DRIFT',
  'UNVERIFIABLE',
  'UNSUPPORTED'
};
const _unitRelationships = {
  'same-unit',
  'one-to-one',
  'many-to-one',
  'same_unit',
  'one_to_one',
  'many_to_one',
  'unverifiable'
};
const _emptyContractRefs =
    (<InspectScorerUnitSourceRef>[], <InspectScorerUnitSpanRef>[]);

class InspectMeasurementUnitVerification {
  final String mappingConsistency, scoreUnitRelationship;
  final String definitionScoreCoverage;
  final List<String> doesNotProve;
  final List<InspectScorerUnitContract> contracts;
  final List<InspectScorerUnitSourceRef> sourceRefs;

  const InspectMeasurementUnitVerification._({
    required this.mappingConsistency,
    required this.scoreUnitRelationship,
    required this.definitionScoreCoverage,
    required this.contracts,
    required this.sourceRefs,
    required this.doesNotProve,
  });

  static InspectMeasurementUnitVerification? tryFromJson(Object? value) {
    if (value == null) return null;
    final json = _map(value);
    if (json.isEmpty) return null;
    final schema = json['schema'];
    final contracts = _unitContracts(json['contracts']);
    final reasons = json.containsKey('reason_codes')
        ? _stringList(json['reason_codes'])
        : const <String>[];
    final limits = _stringList(json['does_not_prove']);
    final sourceRefs = _sourceRefs(json['source_pointers']);
    if ((schema != null &&
            schema != 'flywheel.inspect-scorer-unit-analysis/v1') ||
        json['semantic_verification'] != 'UNVERIFIABLE' ||
        contracts == null ||
        reasons == null ||
        limits == null ||
        sourceRefs == null ||
        (contracts.isEmpty &&
            (reasons.length != 1 || reasons.single != 'no_unit_contract'))) {
      return null;
    }
    final first = contracts.isEmpty ? null : contracts.first;
    final mapping = _unitStatus(json['mapping_consistency']) ??
        first?.mappingConsistency ??
        _unitStatus(json['status']) ??
        'UNVERIFIABLE';
    final relationship = _relationship(json['score_unit_relationship']) ??
        first?.scoreUnitRelationship ??
        'unverifiable';
    final coverage = _unitStatus(json['definition_score_coverage']) ??
        first?.definitionScoreCoverage ??
        'UNVERIFIABLE';
    return InspectMeasurementUnitVerification._(
      mappingConsistency: mapping,
      scoreUnitRelationship: relationship,
      definitionScoreCoverage: coverage,
      contracts: contracts,
      sourceRefs: sourceRefs,
      doesNotProve: limits,
    );
  }
}

class InspectScorerUnitContract {
  final String scorer, actualScoreUnit, declaredIntendedUnit;
  final String mappingConsistency, scoreUnitRelationship;
  final String definitionScoreCoverage;
  final int sourceRows, coveredSourceRows, excludedSourceRows;
  final int mappedDefinitions, actualScoreCardinality;
  final int declaredIntendedCardinality;
  final List<String> reasonCodes;
  final List<InspectScorerUnitSourceRef> sourceRefs;
  final List<InspectScorerUnitSpanRef> spanRefs;

  const InspectScorerUnitContract._({
    required this.scorer,
    required this.actualScoreUnit,
    required this.declaredIntendedUnit,
    required this.mappingConsistency,
    required this.scoreUnitRelationship,
    required this.definitionScoreCoverage,
    required this.sourceRows,
    required this.coveredSourceRows,
    required this.excludedSourceRows,
    required this.mappedDefinitions,
    required this.actualScoreCardinality,
    required this.declaredIntendedCardinality,
    required this.reasonCodes,
    required this.sourceRefs,
    required this.spanRefs,
  });
}

class InspectScorerUnitSourceRef {
  final String pointer, valueText;
  const InspectScorerUnitSourceRef(this.pointer, this.valueText);
}

class InspectScorerUnitSpanRef {
  final String unitId, containerPointer, containerHash, sourceHash, sourceValue;
  final int start, end;
  const InspectScorerUnitSpanRef({
    required this.unitId,
    required this.containerPointer,
    required this.containerHash,
    required this.sourceHash,
    required this.sourceValue,
    required this.start,
    required this.end,
  });
}

List<InspectScorerUnitContract>? _unitContracts(Object? value) {
  if (value is! List) return null;
  final contracts = value.map(_unitContract).toList();
  if (contracts.any((item) => item == null)) return null;
  return List.unmodifiable(contracts.cast<InspectScorerUnitContract>());
}

InspectScorerUnitContract? _unitContract(Object? value) {
  final json = _map(value);
  if (json.isEmpty) return null;
  final scorer = _text(json['scorer']);
  final actualUnit = _text(json['actual_score_unit']);
  final intendedUnit = _text(json['declared_intended_unit']);
  final mapping = _unitStatus(json['mapping_consistency']);
  final relationship = _relationship(json['score_unit_relationship']);
  final coverage = _unitStatus(json['definition_score_coverage']);
  final reasons = _reasonCodes(json['mapping_consistency']);
  if ([scorer, actualUnit, intendedUnit].any((item) => item.isEmpty) ||
      mapping == null ||
      relationship == null ||
      coverage == null ||
      reasons == null) {
    return null;
  }
  final counts = [
    _nonnegative(json['source_rows']),
    _nonnegative(json['scored_source_rows_for_named_scorer']),
    _nonnegative(json['covered_source_rows']),
    _nonnegative(json['excluded_source_rows']),
    _nonnegative(json['mapped_definitions']),
    _nonnegative(json['actual_score_cardinality']),
    _nonnegative(json['declared_intended_cardinality']),
  ];
  if (counts.any((item) => item == null)) return null;
  final mappedDefinitions = counts[4]!;
  final refs = _contractSourceRefs(
    json['source_item_mapping'],
    mappedDefinitions,
  );
  if (refs == null) return null;
  return InspectScorerUnitContract._(
    scorer: scorer,
    actualScoreUnit: actualUnit,
    declaredIntendedUnit: intendedUnit,
    mappingConsistency: mapping,
    scoreUnitRelationship: relationship,
    definitionScoreCoverage: coverage,
    sourceRows: counts[0]!,
    coveredSourceRows: counts[2]!,
    excludedSourceRows: counts[3]!,
    mappedDefinitions: mappedDefinitions,
    actualScoreCardinality: counts[5]!,
    declaredIntendedCardinality: counts[6]!,
    reasonCodes: List.unmodifiable(reasons),
    sourceRefs: refs.$1,
    spanRefs: refs.$2,
  );
}

(List<InspectScorerUnitSourceRef>, List<InspectScorerUnitSpanRef>)?
    _contractSourceRefs(Object? value, int expectedMapped) {
  if (value == null) {
    return expectedMapped == 0 ? _emptyContractRefs : null;
  }
  if (value is! List) return null;
  final sourceRefs = <InspectScorerUnitSourceRef>[];
  final spanRefs = <InspectScorerUnitSpanRef>[];
  var parsed = 0;
  for (final item in value) {
    if (item is! Map) return null;
    final mapping = Map<String, Object?>.from(item);
    final row = _map(mapping['source_row']);
    if (row.isEmpty) return null;
    for (final key in const ['sample_id_ref', 'epoch_ref', 'score_ref']) {
      final ref = row.containsKey(key) ? _sourceRef(row[key]) : null;
      if (ref == null) return null;
      sourceRefs.add(ref);
    }
    final definitions = _map(mapping['mapped_definitions']);
    final refs = definitions['refs'];
    final count = _nonnegative(definitions['count']);
    if (_text(definitions['unit']).isEmpty ||
        count == null ||
        refs is! List ||
        count != refs.length) {
      return null;
    }
    parsed += refs.length;
    for (final rawRef in refs) {
      if (rawRef is! Map) return null;
      final span = _spanRef(Map<String, Object?>.from(rawRef));
      if (span == null) return null;
      spanRefs.add(span);
    }
  }
  if (parsed != expectedMapped) return null;
  return (List.unmodifiable(sourceRefs), List.unmodifiable(spanRefs));
}

List<InspectScorerUnitSourceRef>? _sourceRefs(Object? value) {
  if (value == null) return const <InspectScorerUnitSourceRef>[];
  if (value is! List) return null;
  final refs = value.map(_sourceRef).toList();
  if (refs.any((item) => item == null)) return null;
  return List.unmodifiable(refs.cast<InspectScorerUnitSourceRef>());
}

InspectScorerUnitSourceRef? _sourceRef(Object? value) {
  final json = _map(value);
  final pointer = _text(json['json_pointer']);
  if (pointer.isEmpty || !json.containsKey('source_value')) return null;
  return InspectScorerUnitSourceRef(
      pointer, _displayValue(json['source_value']));
}

InspectScorerUnitSpanRef? _spanRef(Map<String, Object?> ref) {
  final unitId = _text(ref['unit_id']);
  final source = _map(ref['source']);
  final span = _map(source['span']);
  final start = _nonnegative(span['start']);
  final end = _nonnegative(span['end']);
  final containerPointer = _text(source['container_pointer']);
  final containerHash = _text(source['container_value_sha256']);
  final sourceHash = _text(source['source_value_sha256']);
  final sourceValue = source['source_value'];
  if (unitId.isEmpty ||
      containerPointer.isEmpty ||
      span['encoding'] != 'json-string-codepoints-v1' ||
      start == null ||
      end == null ||
      end < start ||
      !_sha256.hasMatch(containerHash) ||
      !_sha256.hasMatch(sourceHash) ||
      sourceValue is! String) {
    return null;
  }
  return InspectScorerUnitSpanRef(
    unitId: unitId,
    containerPointer: containerPointer,
    containerHash: containerHash,
    sourceHash: sourceHash,
    sourceValue: sourceValue,
    start: start,
    end: end,
  );
}

String? _unitStatus(Object? value) {
  final raw = value is Map ? value['status'] : value;
  return raw is String && _unitStatuses.contains(raw) ? raw : null;
}

String? _relationship(Object? value) {
  final raw = value is Map ? value['status'] : value;
  return raw is String && _unitRelationships.contains(raw) ? raw : null;
}

List<String>? _reasonCodes(Object? value) {
  if (value == null || value is String) return const <String>[];
  if (value is Map) return _stringList(value['reason_codes']);
  return null;
}

List<String>? _stringList(Object? value) {
  if (value is! List || value.any((item) => item is! String || item.isEmpty)) {
    return null;
  }
  return List.unmodifiable(value.cast<String>());
}
