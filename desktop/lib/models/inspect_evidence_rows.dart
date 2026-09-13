part of 'inspect_evidence_models.dart';

class InspectEvidenceRow {
  final String pointer, sampleId, scorerName, reportedStatus, sourceValueText;
  final String scoreValueText, scoreHistoryLabel, scoreHistoryState;
  final bool scoreHistoryInvalid;
  final List<String> errors;
  const InspectEvidenceRow({
    required this.pointer,
    required this.sampleId,
    required this.scorerName,
    required this.reportedStatus,
    required this.sourceValueText,
    required this.scoreValueText,
    required this.scoreHistoryLabel,
    required this.scoreHistoryState,
    required this.scoreHistoryInvalid,
    required this.errors,
  });
  String get label =>
      pointer.isNotEmpty ? pointer : [sampleId, scorerName].join(' ').trim();
  String get preview {
    if (sourceValueText.isEmpty) return 'no source value reported';
    if (sourceValueText.length <= 96) return sourceValueText;
    return '${sourceValueText.substring(0, 96)}... '
        '(open for full ${sourceValueText.length} chars)';
  }
}

List<InspectEvidenceRow> _evidenceRows(Map<String, Object?> report) {
  final rows = <InspectEvidenceRow>[];
  for (final item in _maps(report['source_pointers'])) {
    rows.add(_row(item));
  }
  for (final sample in _maps(report['samples'])) {
    final scores = _maps(sample['scores']);
    if (scores.isEmpty) rows.add(_row(sample));
    for (final score in scores) {
      rows.add(_row({...sample, ...score}));
    }
  }
  return List.unmodifiable(rows);
}

InspectEvidenceRow _row(Map<String, Object?> json) {
  final history = inspectScoreHistoryRow(json);
  return InspectEvidenceRow(
    pointer: _text(json['json_pointer'] ??
        json['pointer'] ??
        json['source_pointer'] ??
        json['path']),
    sampleId: _text(json['sample_id'] ?? json['id']),
    scorerName: _text(json['scorer'] ??
        json['scorer_name'] ??
        json['score_name'] ??
        json['name']),
    reportedStatus: _text(
      json['reported_status'] ?? json['status'],
      fallback: 'reported',
    ),
    sourceValueText: json.containsKey('source_value')
        ? _displayValue(json['source_value'])
        : '',
    scoreValueText: json.containsKey('score_value')
        ? _displayValue(json['score_value'])
        : json.containsKey('value')
            ? _displayValue(json['value'])
            : '',
    scoreHistoryLabel: history.label,
    scoreHistoryState: history.state,
    scoreHistoryInvalid: history.invalid,
    errors: _strings(json['errors'] ?? json['error']),
  );
}
