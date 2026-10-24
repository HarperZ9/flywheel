// evidence_extensions.dart -- typed decoders for the contextual
// Journey extensions. Absent, unknown, or execution-locked capabilities
// decode to hidden; Flutter renders only what the server advertises and
// never derives a verdict or a composite from these rows.
import '../client/gateway_error.dart';
import 'scope_field.dart';

class EvidenceCapability {
  final String id, schema, state, reason, contractSha256;
  final List<String> operations;
  final Map<String, dynamic> limits;

  const EvidenceCapability({
    required this.id,
    required this.schema,
    required this.state,
    required this.reason,
    required this.contractSha256,
    required this.operations,
    required this.limits,
  });

  bool get executionLocked => state == 'execution_locked';

  /// A typed state renders (locked states state their lock); an unknown
  /// state hides.
  bool get renderable =>
      const {'available', 'data_only', 'execution_locked', 'read_only'}
          .contains(state);

  static EvidenceCapability? fromJson(Map<String, dynamic> j) {
    final id = j['id'];
    final schema = j['schema'];
    final state = j['state'];
    final reason = j['reason'];
    final contractSha = j['contract_sha256'];
    final operations = j['operations'];
    final limits = j['limits'];
    if (id is! String ||
        schema is! String ||
        state is! String ||
        reason is! String ||
        contractSha is! String ||
        operations is! List ||
        limits is! Map) {
      return null;
    }
    return EvidenceCapability(
      id: id,
      schema: schema,
      state: state,
      reason: reason,
      contractSha256: contractSha,
      operations: operations.whereType<String>().toList(),
      limits: Map<String, dynamic>.from(limits),
    );
  }
}

class EvidenceCapabilities {
  final List<EvidenceCapability> capabilities;
  const EvidenceCapabilities({required this.capabilities});

  EvidenceCapability? byId(String id) {
    for (final c in capabilities) {
      if (c.id == id) return c;
    }
    return null;
  }

  static EvidenceCapabilities fromJson(Map<String, dynamic> j) {
    final rows = j['capabilities'];
    final parsed = rows is List
        ? rows
            .whereType<Map<String, dynamic>>()
            .map(EvidenceCapability.fromJson)
            .whereType<EvidenceCapability>()
            .toList()
        : <EvidenceCapability>[];
    return EvidenceCapabilities(capabilities: parsed);
  }
}

class IncidentProposal {
  final String proposalId, state, journeyRef, scope;
  const IncidentProposal({
    required this.proposalId,
    required this.state,
    required this.journeyRef,
    required this.scope,
  });

  static IncidentProposal? fromJson(Map<String, dynamic> j) {
    final id = j['proposal_id'];
    final state = j['state'];
    final ref = j['journey_ref'];
    // v1 proposals name the scope string by the older key; v2 use `scope`.
    final scope = scopeOf(j);
    if (id is! String ||
        state is! String ||
        ref is! String ||
        scope is! String ||
        (j.containsKey(kScopeKey) && j.containsKey(kLegacyScopeKey))) {
      return null;
    }
    return IncidentProposal(
        proposalId: id, state: state, journeyRef: ref, scope: scope);
  }
}

class FrontierAxis {
  final String axis;
  final Map<String, dynamic> fields;
  final List<String> rawUnrecognized;
  const FrontierAxis({
    required this.axis,
    required this.fields,
    required this.rawUnrecognized,
  });

  static FrontierAxis? fromJson(Map<String, dynamic> j) {
    final axis = j['axis'];
    final fields = j['fields'];
    final raw = j['raw_unrecognized'];
    if (axis is! String ||
        fields is! Map<String, dynamic> ||
        raw is! List) {
      return null;
    }
    return FrontierAxis(
        axis: axis,
        fields: fields,
        rawUnrecognized: raw.whereType<String>().toList());
  }
}

class FrontierAxes {
  final String claimId;
  final List<FrontierAxis> axes;
  const FrontierAxes({required this.claimId, required this.axes});

  static FrontierAxes? fromJson(Map<String, dynamic> j) {
    final id = j['claim_id'];
    final rows = j['axes'];
    if (id is! String || rows is! List) return null;
    return FrontierAxes(
      claimId: id,
      axes: rows
          .whereType<Map<String, dynamic>>()
          .map(FrontierAxis.fromJson)
          .whereType<FrontierAxis>()
          .toList(),
    );
  }
}

class DomainPackProjection {
  final String packSha, state, scope;
  final Map<String, dynamic> qa;
  const DomainPackProjection({
    required this.packSha,
    required this.state,
    required this.scope,
    required this.qa,
  });

  static DomainPackProjection? fromJson(Map<String, dynamic> j) {
    final pack = j['pack'];
    final qa = j['qa'];
    if (pack is! Map<String, dynamic> || qa is! Map<String, dynamic>) {
      return null;
    }
    final sha = pack['pack_sha256'];
    final state = pack['state'];
    // A pack manifest states its scope as a list (v1 under the older key,
    // v2 under `scope`); a single string is read as one entry.
    final scope = scopeOf(pack);
    if (sha is! String ||
        state is! String ||
        (scope is! String && scope is! List) ||
        (scope is List && scope.any((row) => row is! String))) {
      return null;
    }
    return DomainPackProjection(
        packSha: sha, state: state, scope: scopeText(pack), qa: qa);
  }
}

/// The typed transport error the extensions client surfaces.
class EvidenceExtensionFailure implements Exception {
  final String code, message;
  const EvidenceExtensionFailure(this.code, this.message);
  @override
  String toString() => message;
}

EvidenceExtensionFailure evidenceExtensionFailureFrom(Object error) {
  if (error is GatewayException && error.errorCode != null) {
    return EvidenceExtensionFailure(error.errorCode!, error.message);
  }
  return const EvidenceExtensionFailure(
      'INVALID_RESPONSE', 'extension response was invalid');
}
