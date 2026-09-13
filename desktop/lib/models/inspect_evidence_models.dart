import 'dart:convert';

import 'inspect_evidence_upload.dart';

export 'inspect_evidence_upload.dart';

part 'inspect_evidence_list.dart';

final _sha256 = RegExp(r'^[0-9a-f]{64}$');

class InspectImportResult {
  static const schemaName = 'flywheel.inspect-import-result/v1';
  final InspectImportSource? source;
  final String dataRef;
  final InspectEvidenceReport? report;
  final InspectStoreReceipt? stored;
  final String? errorCode, errorMessage;

  const InspectImportResult._({
    this.source,
    this.dataRef = '',
    this.report,
    this.stored,
    this.errorCode,
    this.errorMessage,
  });

  const InspectImportResult.error(String code, String message)
      : this._(errorCode: code, errorMessage: message);

  factory InspectImportResult.fromJson(Map<String, Object?> json) {
    final error = _map(json['error']);
    if (error.isNotEmpty) {
      return InspectImportResult._(
        errorCode: _text(error['code'], fallback: 'GATEWAY_ERROR'),
        errorMessage:
            _text(error['message'], fallback: 'Inspect import could not run.'),
      );
    }
    if (json['schema'] != schemaName) {
      return _invalidResponse();
    }
    final source = InspectImportSource.tryFromJson(_map(json['source']));
    if (source == null) return _invalidResponse();
    final dataRef = _text(json['data_ref']);
    if (dataRef != inspectEvidenceDataRef(source.sha256)) {
      return _invalidResponse();
    }
    final report =
        InspectEvidenceReport.tryFromJson(_map(json['report']), source);
    if (report == null) return _invalidResponse();
    final storedJson = _map(json['stored']);
    final stored =
        storedJson.isEmpty ? null : InspectStoreReceipt.tryFromJson(storedJson);
    if (storedJson.isNotEmpty && stored == null) return _invalidResponse();
    return InspectImportResult._(
      source: source,
      dataRef: dataRef,
      report: report,
      stored: stored,
    );
  }

  bool matchesUpload(InspectEvidenceUpload upload) =>
      errorCode != null ||
      (source?.sha256 == upload.sha256 &&
          source?.byteLength == upload.byteLength &&
          dataRef == upload.dataRef &&
          report?.source.sameIdentity(source!) == true);
}

InspectImportResult _invalidResponse() => const InspectImportResult.error(
      'INVALID_RESPONSE',
      'Gateway returned an incomplete Inspect import result.',
    );

class InspectImportSource {
  final String format, sha256, filename;
  final int byteLength;
  const InspectImportSource._(
      this.format, this.sha256, this.byteLength, this.filename);

  static InspectImportSource? tryFromJson(Map<String, Object?> json) {
    final format = _text(json['format'], fallback: 'inspect-json');
    final sha = _text(json['sha256']);
    final length = _int(json['byte_length']);
    final rawFilename = json['filename'];
    if (format != 'inspect-json' ||
        !_sha256.hasMatch(sha) ||
        length < 1 ||
        length > maxInspectEvidenceUploadBytes ||
        (rawFilename != null && rawFilename is! String)) {
      return null;
    }
    final filename = inspectDisplayFilename(rawFilename as String?);
    if (rawFilename != null && filename == null) return null;
    return InspectImportSource._(format, sha, length, filename ?? '');
  }

  bool sameIdentity(InspectImportSource other) =>
      sha256 == other.sha256 && byteLength == other.byteLength;
}

class InspectStoreReceipt {
  final String kind, eid, sha256, chainHash;
  const InspectStoreReceipt._(this.kind, this.eid, this.sha256, this.chainHash);

  static InspectStoreReceipt? tryFromJson(Map<String, Object?> json) {
    final receipt = InspectStoreReceipt._(
      _text(json['kind']),
      _text(json['eid']),
      _text(json['sha256']),
      _text(json['chain_hash']),
    );
    return receipt.present ? receipt : null;
  }

  bool get present =>
      kind == 'inspect-evidence' &&
      eid.isNotEmpty &&
      _sha256.hasMatch(sha256) &&
      _sha256.hasMatch(chainHash);
}

class InspectEvidenceReport {
  static const schemaName = 'flywheel.inspect-evidence/v1';
  final String reportedStatus, assessment, semanticVerification;
  final InspectImportSource source;
  final bool invalidated;
  final bool? coverageComplete;
  final int? totalSamples, completedSamples, observedSamples;
  final List<InspectEvidenceRow> rows;

  const InspectEvidenceReport._({
    required this.reportedStatus,
    required this.assessment,
    required this.semanticVerification,
    required this.source,
    required this.invalidated,
    required this.coverageComplete,
    required this.totalSamples,
    required this.completedSamples,
    required this.observedSamples,
    required this.rows,
  });

  static InspectEvidenceReport? tryFromJson(
    Map<String, Object?> json,
    InspectImportSource expected,
  ) {
    final source = InspectImportSource.tryFromJson(_map(json['source']));
    final status = _text(json['reported_status']);
    final assessment = _text(json['assessment']);
    if (json['schema'] != schemaName ||
        source == null ||
        !source.sameIdentity(expected) ||
        status.isEmpty ||
        assessment.isEmpty) {
      return null;
    }
    final counts = _map(json['counts']);
    final coverage = _map(json['scoring_coverage']);
    return InspectEvidenceReport._(
      reportedStatus: status,
      assessment: assessment,
      semanticVerification: 'UNVERIFIABLE',
      source: source,
      invalidated: json['invalidated'] == true,
      coverageComplete: coverage['coverage_complete'] is bool
          ? coverage['coverage_complete'] as bool
          : null,
      totalSamples: _intOrNull(counts['total_samples']),
      completedSamples: _intOrNull(counts['completed_samples']),
      observedSamples: _intOrNull(counts['observed_samples']),
      rows: _evidenceRows(json),
    );
  }

  String get countsLabel {
    final observed = observedSamples?.toString() ?? '?';
    final total = totalSamples?.toString() ?? '?';
    final completed = completedSamples?.toString() ?? '?';
    return 'samples $observed/$total · completed $completed';
  }
}

class InspectEvidenceRow {
  final String pointer, sampleId, scorerName, reportedStatus, sourceValueText;
  final String scoreValueText;
  final List<String> errors;
  const InspectEvidenceRow({
    required this.pointer,
    required this.sampleId,
    required this.scorerName,
    required this.reportedStatus,
    required this.sourceValueText,
    required this.scoreValueText,
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

InspectEvidenceRow _row(Map<String, Object?> json) => InspectEvidenceRow(
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
      errors: _strings(json['errors'] ?? json['error']),
    );

Map<String, Object?> _map(Object? value) =>
    value is Map ? Map<String, Object?>.from(value) : <String, Object?>{};

List<Map<String, Object?>> _maps(Object? value) => value is List
    ? [
        for (final item in value)
          if (item is Map) Map<String, Object?>.from(item)
      ]
    : const [];

List<String> _strings(Object? value) {
  if (value is String && value.isNotEmpty) return [value];
  if (value is Map && value['message'] is String) {
    return [value['message'] as String];
  }
  if (value != null && value is! List) return [_displayValue(value)];
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item != null) _displayValue(item)
  ];
}

String _text(Object? value, {String fallback = ''}) =>
    value is String && value.isNotEmpty ? value : fallback;

int _int(Object? value) => value is int ? value : 0;

int? _intOrNull(Object? value) => value is int ? value : null;

String _displayValue(Object? value) {
  if (value == null) return 'null';
  if (value is String) return value;
  try {
    return jsonEncode(value);
  } on Object {
    return '$value';
  }
}
