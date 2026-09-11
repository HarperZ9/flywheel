part of 'operation_models.dart';

final class OperationListPage {
  final String journeyRef, eventHeadSha256;
  final List<OperationSnapshot> operations;
  final Map<String, String> requestSha256ByOperation;
  final String? nextCursor;

  const OperationListPage._(
    this.journeyRef,
    this.eventHeadSha256,
    this.operations,
    this.requestSha256ByOperation,
    this.nextCursor,
  );

  factory OperationListPage.fromJson(Map<String, Object?> json) {
    const fields = {
      'schema',
      'journey_ref',
      'event_head_sha256',
      'operations',
      'request_sha256_by_operation',
      'next_cursor',
    };
    if (json.keys.toSet().length != fields.length ||
        !json.keys.every(fields.contains) ||
        json['schema'] != operationListSchema) {
      _invalid();
    }
    final journey = json['journey_ref'];
    final head = json['event_head_sha256'];
    final rows = json['operations'];
    final requestMap = json['request_sha256_by_operation'];
    final cursor = json['next_cursor'];
    if (journey is! String ||
        !_journeyRef.hasMatch(journey) ||
        head is! String ||
        !sha256Pattern.hasMatch(head) ||
        rows is! List ||
        requestMap is! Map ||
        requestMap.keys.any((key) => key is! String) ||
        requestMap.values.any((value) => value is! String) ||
        (cursor != null &&
            (cursor is! String ||
                cursor.isEmpty ||
                cursor.length > 512 ||
                !isSafePublicText(cursor)))) {
      _invalid();
    }
    final parsed = <OperationSnapshot>[];
    for (final row in rows) {
      if (row is! Map || row.keys.any((key) => key is! String)) _invalid();
      final snapshot = OperationSnapshot.fromJson(
        Map<String, Object?>.from(row),
      );
      if (snapshot.journeyRef != journey || snapshot.canCancel) _invalid();
      parsed.add(snapshot);
    }
    final requestSha = <String, String>{};
    final operations = parsed.map((snapshot) => snapshot.operationRef).toSet();
    if (operations.length != parsed.length ||
        requestMap.length != operations.length) {
      _invalid();
    }
    for (final entry in requestMap.entries) {
      final key = entry.key as String;
      final value = entry.value as String;
      if (!operations.contains(key) ||
          !operationRefPattern.hasMatch(key) ||
          !sha256Pattern.hasMatch(value)) {
        _invalid();
      }
      requestSha[key] = value;
    }
    return OperationListPage._(
      journey,
      head,
      List<OperationSnapshot>.unmodifiable(parsed),
      Map<String, String>.unmodifiable(requestSha),
      cursor as String?,
    );
  }

  Map<String, Object?> toJson() => {
        'schema': operationListSchema,
        'journey_ref': journeyRef,
        'event_head_sha256': eventHeadSha256,
        'operations': operations.map((snapshot) => snapshot.toJson()).toList(),
        'request_sha256_by_operation': requestSha256ByOperation,
        'next_cursor': nextCursor,
      };
}
