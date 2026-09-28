import 'canonical_json.dart';
import 'effect_source_summary.dart';

const effectEvidenceSchema = 'flywheel.gateway-effect-evidence/v1';
const _traceMaxRecords = 2048;
const _traceGenesis =
    '0000000000000000000000000000000000000000000000000000000000000000';

Never _invalid() =>
    throw const FormatException('Gateway effect evidence is invalid');

final class EffectEvidence {
  final EffectBasis basis;
  final int knownObservationCount, knownObservationsOmitted;
  final String knownObservationsDigest;
  final List<EffectObservation> knownObservations;
  final EffectSourceSummary actionWitness, toolCallReceipts;
  final List<String> unknownEffectScope, doesNotProve;

  const EffectEvidence._(
      this.basis,
      this.knownObservationCount,
      this.knownObservationsOmitted,
      this.knownObservationsDigest,
      this.knownObservations,
      this.actionWitness,
      this.toolCallReceipts,
      this.unknownEffectScope,
      this.doesNotProve);

  factory EffectEvidence.fromJson(Object? raw,
      {required String traceRef,
      required int recordCount,
      required String traceHeadSha256,
      required String terminalState}) {
    final value = _map(raw);
    _fields(value, const {
      'schema',
      'scope',
      'basis',
      'known_observation_count',
      'known_observations_omitted',
      'known_observations_digest',
      'known_observations',
      'action_witness',
      'tool_call_receipts',
      'unknown_effect_scope',
      'does_not_prove',
    });
    if (value['schema'] != effectEvidenceSchema ||
        value['scope'] != 'owner_private_trace_prefix') {
      _invalid();
    }
    final basis = EffectBasis.fromJson(_map(value['basis']));
    if (basis.traceRef != traceRef ||
        basis.recordCount != recordCount ||
        basis.traceHeadSha256 != traceHeadSha256 ||
        basis.terminalState != terminalState) {
      _invalid();
    }
    final count = _count(value['known_observation_count']);
    final omitted = _count(value['known_observations_omitted']);
    final rawObservations = value['known_observations'];
    if (rawObservations is! List || rawObservations.length > 64) _invalid();
    final visibleCount = rawObservations.length;
    if (visibleCount != (count < 64 ? count : 64) ||
        omitted != count - visibleCount ||
        count > recordCount) {
      _invalid();
    }
    final observations = List<EffectObservation>.unmodifiable(rawObservations
        .map((item) => EffectObservation.fromJson(_map(item), basis)));
    for (var i = 1; i < observations.length; i++) {
      if (observations[i - 1].traceSequence >= observations[i].traceSequence) {
        _invalid();
      }
    }
    final digest = _sha(value['known_observations_digest']);
    if (omitted == 0 && canonicalJsonSha256(rawObservations) != digest) {
      _invalid();
    }
    return EffectEvidence._(
        basis,
        count,
        omitted,
        digest,
        observations,
        EffectSourceSummary.fromJson(
            _map(value['action_witness']), EffectSourceKind.actionWitness,
            recordCount: basis.recordCount),
        EffectSourceSummary.fromJson(
            _map(value['tool_call_receipts']), EffectSourceKind.toolReceipts,
            recordCount: basis.recordCount),
        _requiredStrings(value['unknown_effect_scope'], const {
          'NOT_ROLLBACK',
          'NOT_EFFECT_ABSENCE',
          'NOT_CURRENT_FILESYSTEM_STATE',
          'UNRECORDED_ACTIONS_NOT_EXCLUDED',
          'TOOLS_WITHOUT_POST_EFFECT_FINGERPRINTS_REMAIN_UNKNOWN',
          'EFFECTS_AFTER_TRACE_HEAD_REMAIN_UNKNOWN',
        }),
        _requiredStrings(value['does_not_prove'], const {
          'semantic correctness',
          'complete workstation observation',
          'current filesystem state',
          'absence of effects outside the accepted trace prefix',
          'rollback or remote cancellation',
        }));
  }
}

final class EffectBasis {
  final String traceRef, traceHeadSha256;
  final String terminalState, terminalBasisEventType, terminalBasisEventSha256;
  final int recordCount;

  const EffectBasis._(this.traceRef, this.recordCount, this.traceHeadSha256,
      this.terminalState, this.terminalBasisEventType,
      this.terminalBasisEventSha256);

  factory EffectBasis.fromJson(Map<String, dynamic> value) {
    _fields(value, const {
      'trace_ref',
      'record_count',
      'trace_head_sha256',
      'terminal_state',
      'terminal_basis_event_type',
      'terminal_basis_event_sha256',
    });
    final count = _count(value['record_count']);
    final head = _sha(value['trace_head_sha256']);
    final state = value['terminal_state'];
    final basis = value['terminal_basis_event_type'];
    if (!const {'completed', 'failed', 'cancelled'}.contains(state) ||
        !const {'operation_queued', 'operation_started', 'cancel_requested'}
            .contains(basis) ||
        (count == 0 && head != _traceGenesis)) {
      _invalid();
    }
    return EffectBasis._(_ref(value['trace_ref'], 'agt'), count, head,
        state as String, basis as String,
        _sha(value['terminal_basis_event_sha256']));
  }
}

final class EffectObservation {
  final String kind, recordSha256, recordKind, payloadKind;
  final String jsonPointer, valueSha256;
  final int traceSequence;

  const EffectObservation._(this.kind, this.traceSequence, this.recordSha256,
      this.recordKind, this.payloadKind, this.jsonPointer, this.valueSha256);

  factory EffectObservation.fromJson(
      Map<String, dynamic> value, EffectBasis basis) {
    _fields(value, const {
      'kind',
      'trace_sequence',
      'record_sha256',
      'record_kind',
      'payload_kind',
      'json_pointer',
      'value_sha256',
    });
    final sequence = value['trace_sequence'];
    if (value['kind'] != 'tool_result_edit_fingerprint' ||
        value['record_kind'] != 'ledger' ||
        value['payload_kind'] != 'tool_result' ||
        value['json_pointer'] != '/payload/meta/edited' ||
        sequence is! int ||
        sequence < 0 ||
        sequence >= basis.recordCount) {
      _invalid();
    }
    return EffectObservation._(
        value['kind'] as String,
        sequence,
        _sha(value['record_sha256']),
        value['record_kind'] as String,
        value['payload_kind'] as String,
        value['json_pointer'] as String,
        _sha(value['value_sha256']));
  }
}

Map<String, dynamic> _map(Object? value) =>
    value is Map<String, dynamic> ? value : _invalid();

int _count(Object? value) {
  if (value is! int || value < 0 || value > _traceMaxRecords) _invalid();
  return value;
}

String _sha(Object? value) {
  if (value is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(value)) {
    _invalid();
  }
  return value;
}

String _ref(Object? value, String prefix) {
  if (value is! String || !RegExp('^${prefix}_[0-9a-f]{32}\$').hasMatch(value)) {
    _invalid();
  }
  return value;
}

void _fields(Map<String, dynamic> value, Set<String> fields) {
  if (value.length != fields.length || !value.keys.every(fields.contains)) {
    _invalid();
  }
}

List<String> _requiredStrings(Object? value, Set<String> allowed) {
  if (value is! List ||
      value.length != allowed.length ||
      value.any((item) => item is! String || !allowed.contains(item)) ||
      value.toSet().length != allowed.length) {
    _invalid();
  }
  return List<String>.unmodifiable(value.cast<String>());
}
