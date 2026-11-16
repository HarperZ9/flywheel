part of 'inspect_evidence_models.dart';

class InspectImportList {
  static const schemaName = 'flywheel.inspect-import-list/v1';
  final List<InspectImportListItem> items;
  final String nextCursor;
  final String? errorCode, errorMessage;

  const InspectImportList._({
    this.items = const [],
    this.nextCursor = '',
    this.errorCode,
    this.errorMessage,
  });

  factory InspectImportList.fromJson(Map<String, Object?> json) {
    final error = _map(json['error']);
    if (error.isNotEmpty) {
      return InspectImportList._(
        errorCode: _text(error['code'], fallback: 'GATEWAY_ERROR'),
        errorMessage:
            _text(error['message'], fallback: 'Inspect imports unavailable.'),
      );
    }
    if (json['schema'] != schemaName) {
      return const InspectImportList._(
        errorCode: 'INVALID_RESPONSE',
        errorMessage: 'Gateway returned an incomplete Inspect import list.',
      );
    }
    final items = _maps(json['items']);
    return InspectImportList._(
      items: List.unmodifiable(
        (items.isNotEmpty ? items : _maps(json['imports']))
            .map(InspectImportListItem.fromJson),
      ),
      nextCursor: _text(json['next_cursor'] ?? json['offset']),
    );
  }
}

class InspectImportListItem {
  final String eid, sourceSha256, filename, reportedStatus, storedSha256;
  final int byteLength;
  const InspectImportListItem._({
    required this.eid,
    required this.sourceSha256,
    required this.filename,
    required this.reportedStatus,
    required this.storedSha256,
    required this.byteLength,
  });

  factory InspectImportListItem.fromJson(Map<String, Object?> json) {
    final source = _map(json['source']);
    final stored = _map(json['stored']);
    return InspectImportListItem._(
      eid: _text(json['eid']),
      sourceSha256: _text(json['source_sha256'] ?? source['sha256']),
      filename: _text(json['filename'] ?? source['filename']),
      reportedStatus: _text(json['reported_status'], fallback: 'reported'),
      storedSha256: _text(json['stored_sha256'] ?? stored['sha256']),
      byteLength: _int(json['byte_length'] ?? source['byte_length']),
    );
  }
}
