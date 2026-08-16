import 'dart:convert';

import 'evidence_state.dart';
import 'gateway_grant_summary.dart';

const operationSnapshotSchema = 'flywheel.gateway-operation-snapshot/v1';
const operationResultSchema = 'flywheel.gateway-operation-result/v1';
final _journeyRef = RegExp(r'^jrn_[0-9a-f]{32}$');

enum OperationState {
  proposed,
  approvalRequired,
  queued,
  running,
  cancelRequested,
  cancelled,
  completed,
  failed;

  bool get isTerminal => const {
        OperationState.cancelled,
        OperationState.completed,
        OperationState.failed,
      }.contains(this);
}

OperationState _serverState(Object? raw) => switch (raw) {
      'queued' => OperationState.queued,
      'running' => OperationState.running,
      'cancel_requested' => OperationState.cancelRequested,
      'cancelled' => OperationState.cancelled,
      'completed' => OperationState.completed,
      'failed' => OperationState.failed,
      _ => throw _invalid(),
    };

Never _invalid() =>
    throw ArgumentError('Gateway operation response is invalid');

Object? _freezeJson(Object? value, List<int> budget, int depth) {
  if (depth > 16 || --budget[0] < 0) _invalid();
  if (value == null || value is String || value is bool || value is int) {
    return value;
  }
  if (value is num) return value.isFinite ? value : _invalid();
  if (value is List) {
    return List.unmodifiable(
        value.map((item) => _freezeJson(item, budget, depth + 1)));
  }
  if (value is Map && value.keys.every((key) => key is String)) {
    return Map<String, Object?>.unmodifiable({
      for (final entry in value.entries)
        entry.key as String: _freezeJson(entry.value, budget, depth + 1)
    });
  }
  return _invalid();
}

final class OperationSnapshot {
  final String operationRef, journeyRef, eventHeadSha256;
  final OperationState state;
  final bool canCancel;
  final String? terminalEventRef, resultSha256;

  const OperationSnapshot._(
      this.operationRef,
      this.journeyRef,
      this.eventHeadSha256,
      this.state,
      this.canCancel,
      this.terminalEventRef,
      this.resultSha256);

  factory OperationSnapshot.fromJson(Map<String, Object?> json) {
    const fields = {
      'schema',
      'operation_ref',
      'journey_ref',
      'event_head_sha256',
      'state',
      'can_cancel',
      'terminal_event_ref',
      'result_sha256',
    };
    if (json.keys.toSet().length != fields.length ||
        !json.keys.every(fields.contains) ||
        json['schema'] != operationSnapshotSchema) {
      _invalid();
    }
    final operation = json['operation_ref'];
    final journey = json['journey_ref'];
    final head = json['event_head_sha256'];
    final canCancel = json['can_cancel'];
    final terminal = json['terminal_event_ref'];
    final result = json['result_sha256'];
    if (operation is! String ||
        !operationRefPattern.hasMatch(operation) ||
        journey is! String ||
        !_journeyRef.hasMatch(journey) ||
        head is! String ||
        !sha256Pattern.hasMatch(head) ||
        canCancel is! bool) {
      _invalid();
    }
    final state = _serverState(json['state']);
    _validateState(state, canCancel, terminal, result);
    return OperationSnapshot._(operation, journey, head, state, canCancel,
        terminal as String?, result as String?);
  }

  bool get isTerminal => state.isTerminal;
  GatewayJourneyBinding get binding =>
      GatewayJourneyBinding(journeyRef, eventHeadSha256);

  Map<String, Object?> toJson() => {
        'schema': operationSnapshotSchema,
        'operation_ref': operationRef,
        'journey_ref': journeyRef,
        'event_head_sha256': eventHeadSha256,
        'state': _wireState(state),
        'can_cancel': canCancel,
        'terminal_event_ref': terminalEventRef,
        'result_sha256': resultSha256,
      };

  @override
  bool operator ==(Object other) =>
      other is OperationSnapshot &&
      operationRef == other.operationRef &&
      journeyRef == other.journeyRef &&
      eventHeadSha256 == other.eventHeadSha256 &&
      state == other.state &&
      canCancel == other.canCancel &&
      terminalEventRef == other.terminalEventRef &&
      resultSha256 == other.resultSha256;

  @override
  int get hashCode => Object.hash(operationRef, journeyRef, eventHeadSha256,
      state, canCancel, terminalEventRef, resultSha256);
}

void _validateState(
    OperationState state, bool canCancel, Object? terminal, Object? result) {
  final terminalFields = terminal is String &&
      sha256Pattern.hasMatch(terminal) &&
      result is String &&
      sha256Pattern.hasMatch(result);
  if (state.isTerminal) {
    if (canCancel || !terminalFields) _invalid();
    return;
  }
  if (terminal != null || result != null) _invalid();
  if (canCancel && state != OperationState.running) _invalid();
}

String _wireState(OperationState state) => switch (state) {
      OperationState.proposed => 'proposed',
      OperationState.approvalRequired => 'approval_required',
      OperationState.queued => 'queued',
      OperationState.running => 'running',
      OperationState.cancelRequested => 'cancel_requested',
      OperationState.cancelled => 'cancelled',
      OperationState.completed => 'completed',
      OperationState.failed => 'failed',
    };

final class OperationResult {
  final String operationRef, action;
  final OperationState state;
  final Map<String, Object?> result;

  const OperationResult._(
      this.operationRef, this.action, this.state, this.result);

  factory OperationResult.fromJson(Map<String, Object?> json) {
    const fields = {'schema', 'operation_ref', 'action', 'state', 'result'};
    if (json.keys.toSet().length != fields.length ||
        !json.keys.every(fields.contains) ||
        json['schema'] != operationResultSchema) {
      _invalid();
    }
    final operation = json['operation_ref'];
    final action = json['action'];
    final raw = json['result'];
    final state = _serverState(json['state']);
    if (operation is! String ||
        !operationRefPattern.hasMatch(operation) ||
        action != 'agent.run' ||
        !state.isTerminal ||
        raw is! Map ||
        raw.keys.any((key) => key is! String)) {
      _invalid();
    }
    final frozen = _freezeJson(raw, [4096], 0) as Map<String, Object?>;
    final encoded = utf8.encode(jsonEncode(frozen));
    if (encoded.length > 1048576) _invalid();
    return OperationResult._(operation, action as String, state, frozen);
  }
}

bool allowsOperationTransition(OperationState from, OperationState to) =>
    switch (from) {
      OperationState.queued =>
        {OperationState.running, OperationState.failed}.contains(to),
      OperationState.running => {
          OperationState.cancelRequested,
          OperationState.completed,
          OperationState.failed,
        }.contains(to),
      OperationState.cancelRequested => {
          OperationState.cancelled,
          OperationState.completed,
          OperationState.failed,
        }.contains(to),
      _ => false,
    };
