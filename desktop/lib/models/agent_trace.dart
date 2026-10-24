import 'canonical_json.dart';
import 'effect_evidence.dart';
import 'run_outcome.dart';
import 'scope_field.dart';

const traceProjectionSchema = 'flywheel.gateway-agent-projection/v2';
const traceProjectionSchemaV1 = 'flywheel.gateway-agent-projection/v1';
const traceProjectionSchemas = {traceProjectionSchema, traceProjectionSchemaV1};

/// What a v2 projection covers.
const traceProjectionScope = {
  'TRACE_AS_RECORDED',
  'TOOL_OUTPUT_BOUNDED',
  'ACCEPTED_PREFIX_ONLY_UNTIL_COMPLETED',
};

/// The v1 vocabulary, kept so stored v1 projections still read.
const traceProjectionScopeV1 = {
  'NOT_SEMANTIC_TRUTH',
  'NOT_UNLIMITED_TOOL_OUTPUT',
  'ACCEPTED_PREFIX_ONLY_UNTIL_COMPLETED',
};
const traceMaxRecords = 2048;
const traceMaxRecordBytes = 8 * 1024 * 1024;
const traceMaxBytes = 32 * 1024 * 1024;
const traceMaxResponseBytes = 36 * 1024 * 1024;
const traceMaxJsonNodes = 250000;

final class TraceLimitException extends FormatException {
  const TraceLimitException() : super('Private trace exceeds reader limits');
}

const traceGenesis =
    '0000000000000000000000000000000000000000000000000000000000000000';

Never invalidTrace() =>
    throw const FormatException('Private trace response is invalid');

String traceReference(Object? value, String prefix) {
  if (value is! String ||
      !RegExp('^${prefix}_[0-9a-f]{32}\$').hasMatch(value)) {
    invalidTrace();
  }
  return value;
}

String traceDigest(Object? value) {
  if (value is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(value)) {
    invalidTrace();
  }
  return value;
}

void traceFields(Map<String, dynamic> value, Set<String> fields) {
  if (value.length != fields.length || !value.keys.every(fields.contains)) {
    invalidTrace();
  }
}

List<String> traceCodes(Object? value, Set<String> allowed) {
  if (value is! List ||
      value.length != allowed.length ||
      value.any((item) => item is! String || !allowed.contains(item)) ||
      value.toSet().length != allowed.length) {
    invalidTrace();
  }
  return List<String>.unmodifiable(value);
}

final class TraceProjection {
  final String operationRef, journeyRef, traceRef, state;
  final String traceHeadSha256, projectionSha256;
  final int recordCount;
  final List<String> omissions, scope;
  final String? reason;
  final Map<String, String?>? runtime;
  final EffectEvidence? effectEvidence;
  final RunOutcome? runOutcome;

  const TraceProjection._(
      this.operationRef,
      this.journeyRef,
      this.traceRef,
      this.state,
      this.traceHeadSha256,
      this.projectionSha256,
      this.recordCount,
      this.omissions,
      this.scope,
      this.reason,
      this.runtime,
      this.effectEvidence,
      this.runOutcome);

  factory TraceProjection.fromJson(Map<String, dynamic> value,
      {required String operationRef, required String journeyRef}) {
    final state = value['state'];
    final legacy = value['schema'] == traceProjectionSchemaV1;
    final scopeKey = scopeKeyFor(legacy: legacy);
    traceFields(value, {
      'schema',
      'operation_ref',
      'journey_ref',
      'trace_ref',
      'state',
      'trace_head_sha256',
      'projection_sha256',
      'record_count',
      'omissions',
      scopeKey,
      if (state == 'failed') 'reason',
      if (value.containsKey('runtime')) 'runtime',
      if (value.containsKey('effect_evidence')) 'effect_evidence',
      if (value.containsKey('run_outcome')) 'run_outcome',
    });
    if (!traceProjectionSchemas.contains(value['schema']) ||
        !const {'running', 'completed', 'failed', 'cancelled'}
            .contains(state) ||
        traceReference(value['operation_ref'], 'op') != operationRef ||
        traceReference(value['journey_ref'], 'jrn') != journeyRef) {
      invalidTrace();
    }
    final count = value['record_count'];
    if (count is! int || count < 0 || count > traceMaxRecords) invalidTrace();
    final head = traceDigest(value['trace_head_sha256']);
    if (count == 0 && head != traceGenesis) invalidTrace();
    final digest = traceDigest(value['projection_sha256']);
    final material = Map<String, dynamic>.from(value)
      ..remove('projection_sha256');
    if (canonicalJsonSha256(material) != digest) invalidTrace();
    final reason = value['reason'];
    if (state == 'failed' &&
        (reason is! String ||
            !RegExp(r'^[A-Z][A-Z0-9_]{0,63}$').hasMatch(reason))) {
      invalidTrace();
    }
    final terminalState = state as String;
    final effectEvidence = value.containsKey('effect_evidence')
        ? EffectEvidence.fromJson(value['effect_evidence'],
            traceRef: traceReference(value['trace_ref'], 'agt'),
            recordCount: count,
            traceHeadSha256: head,
            terminalState: terminalState)
        : null;
    if (effectEvidence != null && terminalState == 'running') invalidTrace();
    final runOutcome = value.containsKey('run_outcome')
        ? RunOutcome.fromJson(value['run_outcome'], terminalState: terminalState)
        : null;
    if (runOutcome != null && terminalState == 'running') invalidTrace();
    return TraceProjection._(
        operationRef,
        journeyRef,
        traceReference(value['trace_ref'], 'agt'),
        terminalState,
        head,
        digest,
        count,
        traceCodes(value['omissions'], const {
          'PRIVATE_CONTENT',
          'CREDENTIAL_VALUES',
          'UPSTREAM_OUTPUT_LIMITS',
        }),
        traceCodes(value[scopeKey],
            legacy ? traceProjectionScopeV1 : traceProjectionScope),
        reason as String?,
        value.containsKey('runtime') ? _runtime(value['runtime']) : null,
        effectEvidence,
        runOutcome);
  }

  bool get isRunning => state == 'running';
  bool get isPartialExecution => state != 'completed';
}

Map<String, String?> _runtime(Object? value) {
  if (value is! Map<String, dynamic>) invalidTrace();
  traceFields(value, {'python', 'system', 'architecture'});
  final python = value['python'],
      system = value['system'],
      arch = value['architecture'];
  if ((python != null &&
          (python is! String ||
              !RegExp(r'^[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}$')
                  .hasMatch(python))) ||
      (system != null &&
          !const {'Windows', 'Linux', 'Darwin'}.contains(system)) ||
      (arch != null &&
          !const {'AMD64', 'x86_64', 'arm64', 'aarch64', 'x86', 'i686'}
              .contains(arch))) {
    invalidTrace();
  }
  return Map<String, String?>.unmodifiable(value.cast<String, String?>());
}
