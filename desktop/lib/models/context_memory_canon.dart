part of 'context_memory.dart';

final class ContextMemoryHit {
  ContextMemoryHit._(
      {required this.recordId,
      required this.claimState,
      required this.excerpt,
      required this.excerptTruncated,
      required this.citation});

  final String recordId, claimState, excerpt;
  final bool excerptTruncated;
  final ContextMemoryCitation citation;

  factory ContextMemoryHit.fromJson(
      Map<String, Object?> json, String field, List<ParseIssue> issues) {
    final citationRaw = json['citation'];
    final citation = citationRaw is Map<String, Object?>
        ? ContextMemoryCitation.fromJson(citationRaw, '$field.citation', issues)
        : ContextMemoryCitation.invalid('$field.citation', citationRaw, issues);
    return ContextMemoryHit._(
        recordId: readText(json, 'record_id', issues),
        claimState: readText(json, 'claim_state', issues),
        excerpt: _readBoundedText(json['excerpt'], '$field.excerpt', issues,
            maxLength: 700),
        excerptTruncated:
            readValue<bool>(json, 'excerpt_truncated', issues, false),
        citation: citation);
  }

  String describe() {
    final parts = [
      'record_id=$recordId',
      'claim_state=$claimState',
      'excerpt_truncated=$excerptTruncated',
      'record_key=${citation.recordKey}',
      'event_record_id=${citation.eventRecordId}',
      'source_hash=${citation.sourceHash}',
      if (citation.sourceApp.isNotEmpty) 'source_app=${citation.sourceApp}',
      if (citation.nativeId.isNotEmpty) 'native_id=${citation.nativeId}',
      if (citation.sessionId.isNotEmpty) 'session_id=${citation.sessionId}',
    ];
    return parts.join('; ');
  }
}

final class ContextMemoryCitation {
  ContextMemoryCitation._(
      {required this.recordKey,
      required this.eventRecordId,
      required this.sourceHash,
      required this.sourceApp,
      required this.nativeId,
      required this.sessionId});

  final String recordKey, eventRecordId, sourceHash;
  final String sourceApp, nativeId, sessionId;

  factory ContextMemoryCitation.fromJson(
          Map<String, Object?> json, String field, List<ParseIssue> issues) =>
      ContextMemoryCitation._(
          recordKey: readText(json, 'record_key', issues),
          eventRecordId: readText(json, 'event_record_id', issues),
          sourceHash:
              readText(json, 'source_hash', issues, pattern: sha256Pattern),
          sourceApp: readText(json, 'source_app', issues, optional: true),
          nativeId: readText(json, 'native_id', issues, optional: true),
          sessionId: readText(json, 'session_id', issues, optional: true));

  factory ContextMemoryCitation.invalid(
      String field, Object? raw, List<ParseIssue> issues) {
    addParseIssue(issues, field, raw);
    return ContextMemoryCitation._(
        recordKey: '',
        eventRecordId: '',
        sourceHash: '',
        sourceApp: '',
        nativeId: '',
        sessionId: '');
  }
}

final class ContextMemoryPendingExtraction {
  ContextMemoryPendingExtraction._(
      {required this.eventRecordId, required this.ref, required this.status});

  final String eventRecordId, ref, status;

  factory ContextMemoryPendingExtraction.fromJson(
          Map<String, Object?> json, String field, List<ParseIssue> issues) =>
      ContextMemoryPendingExtraction._(
          eventRecordId: readText(json, 'event_record_id', issues),
          ref: readText(json, 'ref', issues),
          status: readText(json, 'status', issues));

  String describe() =>
      'event_record_id=$eventRecordId; ref=$ref; status=$status';
}

final class ContextMemoryCoverage {
  ContextMemoryCoverage._(
      {required this.recordsSearched,
      required this.matchingRecords,
      required this.hitsOmitted,
      required this.pendingCount,
      required this.pendingReturned,
      required this.method,
      required this.historicalCompleteness,
      required this.sourceFreshness,
      required this.supersessionResolution});

  final int recordsSearched, matchingRecords, hitsOmitted;
  final int pendingCount, pendingReturned;
  final String method, historicalCompleteness, sourceFreshness;
  final String supersessionResolution;

  factory ContextMemoryCoverage.fromResponse(
      Map<String, Object?> json, List<ParseIssue> issues) {
    final canon = json['canon'];
    final raw = canon is Map<String, Object?> ? canon['coverage'] : null;
    if (raw is! Map<String, Object?>) {
      addParseIssue(issues, 'canon.coverage', raw);
      return ContextMemoryCoverage._empty();
    }
    return ContextMemoryCoverage._(
        recordsSearched: _readCount(raw, 'records_searched', issues),
        matchingRecords: _readCount(raw, 'matching_records', issues),
        hitsOmitted: _readCount(raw, 'hits_omitted', issues),
        pendingCount: _readCount(raw, 'pending_count', issues),
        pendingReturned: _readCount(raw, 'pending_returned', issues),
        method: readText(raw, 'method', issues),
        historicalCompleteness:
            readText(raw, 'historical_completeness', issues),
        sourceFreshness: readText(raw, 'source_freshness', issues),
        supersessionResolution:
            readText(raw, 'supersession_resolution', issues));
  }

  factory ContextMemoryCoverage._empty() => ContextMemoryCoverage._(
      recordsSearched: 0,
      matchingRecords: 0,
      hitsOmitted: 0,
      pendingCount: 0,
      pendingReturned: 0,
      method: '',
      historicalCompleteness: '',
      sourceFreshness: '',
      supersessionResolution: '');

  String describe() => 'coverage: records_searched=$recordsSearched; '
      'matching_records=$matchingRecords; hits_omitted=$hitsOmitted; '
      'pending_count=$pendingCount; pending_returned=$pendingReturned; '
      'method=$method; historical_completeness=$historicalCompleteness; '
      'source_freshness=$sourceFreshness; '
      'supersession_resolution=$supersessionResolution';
}

void _validateCanonCaptureReceipt(
    Map<String, Object?> canon, String wrapperStatus, List<ParseIssue> issues) {
  expectSchema(canon, _canonContextIngestSchema, issues);
  final canonStatus = readText(canon, 'status', issues);
  if (canonStatus != wrapperStatus) {
    addParseIssue(issues, 'canon.status', canonStatus);
  }
  readText(canon, 'event_record_id', issues);
  readText(canon, 'source_hash', issues, pattern: sha256Pattern);
}

String _preflightMessage(String status, int hits, int pending, int returned,
    {int currentOmitted = 0}) {
  final omitted = currentOmitted == 0
      ? ''
      : '; $currentOmitted current submission hit${currentOmitted == 1 ? '' : 's'} omitted';
  if (status == 'pending_extraction' && hits == 0) {
    return 'pending extraction: $pending pending, $returned returned$omitted';
  }
  return 'returned $hits reference${hits == 1 ? '' : 's'}'
      '${pending == 0 ? '' : '; $pending pending extraction${pending == 1 ? '' : 's'}'}$omitted';
}

String _readBoundedText(Object? raw, String field, List<ParseIssue> issues,
    {required int maxLength}) {
  if (raw is String) {
    final normalized = raw.replaceAll(RegExp(r'\s+'), ' ').trim();
    final bounded = normalized.length <= maxLength
        ? normalized
        : '${normalized.substring(0, maxLength)}...';
    if (bounded.isNotEmpty && isSafePublicText(bounded)) return bounded;
  }
  addParseIssue(issues, field, raw);
  return '';
}

int _readCount(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is int && raw >= 0) return raw;
  addParseIssue(issues, field, raw);
  return 0;
}
