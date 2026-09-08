import 'evidence_state.dart';
import 'approval_review_models.dart';

const gatewayGrantListRequestSchema = 'flywheel.gateway-grant-list-request/v1';
const gatewayGrantListSchema = 'flywheel.gateway-grant-list/v1';
const gatewayGrantListItemSchema = 'flywheel.gateway-grant-list-item/v1';

final _statePattern = RegExp(r'^[a-z][a-z0-9_]{0,63}$');
const _listStatuses = {
  'complete',
  'legacy_index_required',
  'index_drift',
  'index_mutation_pending',
  'index_unavailable',
  'recovery_required',
};
final _recoveryReasonPattern = RegExp(r'^[A-Z][A-Z0-9_]{0,63}$');

final class GatewayGrantList extends DefensiveModel {
  final String serverTime, state, nextCursor, coverageScope, recoveryRequired;
  final List<GatewayGrantListItem> items;
  final bool indexComplete;
  final String listStatus;
  final int decidedRecentWindowSeconds, inspectedIndexRows, recordReads;

  GatewayGrantList._(
      this.serverTime,
      this.state,
      this.items,
      this.nextCursor,
      this.indexComplete,
      this.listStatus,
      this.coverageScope,
      this.recoveryRequired,
      this.decidedRecentWindowSeconds,
      this.inspectedIndexRows,
      this.recordReads,
      super.parseIssues);

  factory GatewayGrantList.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    _exactFields(
        json,
        const {
          'schema',
          'server_time',
          'state',
          'items',
          'next_cursor',
          'index_complete',
          'list_status',
          'coverage_scope',
          'recovery_required',
          'decided_recent_window_seconds',
          'inspected_index_rows',
          'record_reads'
        },
        const {},
        issues,
        'list');
    expectSchema(json, gatewayGrantListSchema, issues);
    final rawItems = json['items'];
    final items = <GatewayGrantListItem>[];
    if (rawItems is List) {
      for (final (index, item) in rawItems.indexed) {
        if (item is Map<String, Object?>) {
          final parsed = GatewayGrantListItem.fromJson(item, 'items[$index]');
          items.add(parsed);
          issues.addAll(parsed.parseIssues);
        } else {
          addParseIssue(issues, 'items[$index]', item);
        }
      }
    } else {
      addParseIssue(issues, 'items', rawItems);
    }
    final indexComplete =
        readValue<bool>(json, 'index_complete', issues, false);
    final listStatus =
        readText(json, 'list_status', issues, pattern: _statePattern);
    if (!_listStatuses.contains(listStatus)) {
      addParseIssue(issues, 'list_status', json['list_status']);
    }
    final coverageScope =
        readText(json, 'coverage_scope', issues, pattern: _statePattern);
    if (coverageScope != 'maintained_index') {
      addParseIssue(issues, 'coverage_scope', json['coverage_scope']);
    }
    final recoveryRequired = readText(json, 'recovery_required', issues,
        optional: true, pattern: _recoveryReasonPattern);
    if (listStatus == 'recovery_required' && recoveryRequired.isEmpty) {
      addParseIssue(issues, 'recovery_required', json['recovery_required']);
    }
    final decidedWindow =
        readValue<int>(json, 'decided_recent_window_seconds', issues, 0);
    final inspectedRows =
        readValue<int>(json, 'inspected_index_rows', issues, 0);
    final recordReads = readValue<int>(json, 'record_reads', issues, 0);
    for (final (field, value) in [
      ('decided_recent_window_seconds', decidedWindow),
      ('inspected_index_rows', inspectedRows),
      ('record_reads', recordReads),
    ]) {
      if (value < 0) addParseIssue(issues, field, value);
    }
    return GatewayGrantList._(
        readText(json, 'server_time', issues),
        readText(json, 'state', issues, pattern: _statePattern),
        List.unmodifiable(items),
        readText(json, 'next_cursor', issues, optional: true),
        indexComplete,
        listStatus,
        coverageScope,
        recoveryRequired,
        decidedWindow,
        inspectedRows,
        recordReads,
        issues);
  }
}

final class GatewayGrantListItem extends DefensiveModel {
  final String proposalRef, plannedGrantRef, proposalState, derivedState;
  final String recordSha256, expiresAt, operationRef, reviewSha256;
  final String unavailableReason;
  final bool reviewAvailable;
  final Map<String, Object?> summary;

  GatewayGrantListItem._(
      this.proposalRef,
      this.plannedGrantRef,
      this.proposalState,
      this.derivedState,
      this.recordSha256,
      this.expiresAt,
      this.operationRef,
      this.reviewAvailable,
      this.reviewSha256,
      this.unavailableReason,
      this.summary,
      super.parseIssues);

  String summaryText(String key) {
    final value = summary[key];
    return value is String && isSafePublicText(value) ? value : '';
  }

  factory GatewayGrantListItem.fromJson(Map<String, Object?> json,
      [String field = 'item']) {
    final issues = <ParseIssue>[];
    _exactFields(
        json,
        const {
          'schema',
          'proposal_ref',
          'planned_grant_ref',
          'proposal_state',
          'derived_state',
          'record_sha256',
          'expires_at',
          'operation_ref',
          'review_available',
          'summary'
        },
        const {'review_sha256', 'unavailable_reason'},
        issues,
        field);
    expectSchema(json, gatewayGrantListItemSchema, issues);
    final reviewAvailable =
        readValue<bool>(json, 'review_available', issues, false);
    final reviewSha = readText(json, 'review_sha256', issues,
        optional: !reviewAvailable, pattern: sha256Pattern);
    if (reviewAvailable && reviewSha.isEmpty) {
      addParseIssue(issues, 'review_sha256', json['review_sha256']);
    }
    return GatewayGrantListItem._(
        readText(json, 'proposal_ref', issues, pattern: proposalRefPattern),
        readText(json, 'planned_grant_ref', issues, pattern: grantRefPattern),
        readText(json, 'proposal_state', issues, pattern: _statePattern),
        readText(json, 'derived_state', issues, pattern: _statePattern),
        readText(json, 'record_sha256', issues, pattern: sha256Pattern),
        readText(json, 'expires_at', issues),
        readText(json, 'operation_ref', issues,
            optional: true, pattern: operationRefPattern),
        reviewAvailable,
        reviewSha,
        readText(json, 'unavailable_reason', issues, optional: true),
        _readSummary(json['summary'], issues),
        issues);
  }
}

Map<String, Object?> _readSummary(Object? raw, List<ParseIssue> issues) {
  final frozen = freezeApprovalJson(raw, issues, 'summary', [512], 0);
  return frozen is Map<String, Object?> ? frozen : const {};
}

void _exactFields(Map<String, Object?> value, Set<String> required,
    Set<String> optional, List<ParseIssue> issues, String field) {
  final keys = value.keys.toSet();
  if (!required.every(keys.contains) ||
      !keys.every((key) => required.contains(key) || optional.contains(key))) {
    addParseIssue(issues, field, value.keys.toList());
  }
}
