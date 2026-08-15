typedef ParseIssue = ({String field, String? rawValue});

abstract class DefensiveModel {
  final List<ParseIssue> parseIssues;
  const DefensiveModel(this.parseIssues);
  bool get invalidResponse => parseIssues.isNotEmpty;
  bool sameList<T>(List<T> left, List<T> right, bool Function(T, T) same) {
    if (left.length != right.length) return false;
    for (var index = 0; index < left.length; index++) {
      if (!same(left[index], right[index])) return false;
    }
    return true;
  }

  bool sameStringMap(Map<String, String> left, Map<String, String> right) =>
      left.length == right.length &&
      left.entries.every((entry) => right[entry.key] == entry.value);
  bool sameNullableStringMap(
          Map<String, String>? left, Map<String, String>? right) =>
      left == null
          ? right == null
          : right != null && sameStringMap(left, right);
}

final _windowsPath = RegExp(r'[A-Za-z]:[\\/]');
final _uncPath = RegExp(r'(?:\\\\|//)[^\\/\s]+[\\/][^\s]+');
final _privatePath = RegExp(r'(?:^|[\s=(\[{,:;])/(?!/)[^\s]+|/'
    r'(?:Users|home|private|tmp|var|etc|root|opt|mnt|srv|usr|bin|sbin|lib|'
    r'Applications|Volumes|dev|proc|sys|run)(?:/|$)');
final _fileUri = RegExp(r'(?<![A-Za-z0-9+.-])file:', caseSensitive: false);
final _secretValue = RegExp(
    r'(^[A-Za-z0-9_+/=-]{32,}$|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-(?:live|proj|ant)[A-Za-z0-9_-]{10,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b|\b(?:secret|password|passwd|api_key|access_key)\s*[:=]\s*["\x27]?[A-Za-z0-9/+_-]{12,})',
    caseSensitive: false);
final proposalRefPattern = RegExp(r'^prp_[0-9a-f]{32}$');
final grantRefPattern = RegExp(r'^gnt_[0-9a-f]{32}$');
final operationRefPattern = RegExp(r'^op_[0-9a-f]{32}$');
final sha256Pattern = RegExp(r'^[0-9a-f]{64}$');
bool isSafePublicText(String value) =>
    !_windowsPath.hasMatch(value) &&
    !_uncPath.hasMatch(value) &&
    !_privatePath.hasMatch(value) &&
    !_fileUri.hasMatch(value) &&
    !_secretValue.hasMatch(value);
String? safeRawValue(Object? raw) {
  if (raw == null) return null;
  if (raw is String) return isSafePublicText(raw) ? raw : '[redacted]';
  if (raw is num || raw is bool) return raw.toString();
  return '[unsupported ${raw.runtimeType}]';
}

void addParseIssue(List<ParseIssue> issues, String field, Object? raw) =>
    issues.add((field: field, rawValue: safeRawValue(raw)));

void expectSchema(
    Map<String, Object?> json, String expected, List<ParseIssue> issues) {
  if (json['schema'] != expected) {
    addParseIssue(issues, 'schema', json['schema']);
  }
}

String readText(
    Map<String, Object?> json, String field, List<ParseIssue> issues,
    {bool optional = false, RegExp? pattern}) {
  final raw = json[field];
  if (optional && raw == null) return '';
  if (raw is String &&
      raw.isNotEmpty &&
      (pattern == null ? isSafePublicText(raw) : pattern.hasMatch(raw))) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return '';
}

String readDetail(
    Map<String, Object?> json, String field, List<ParseIssue> issues,
    {String fallback = ''}) {
  final raw = json[field];
  if (raw == null) return fallback;
  if (raw is String && isSafePublicText(raw)) return raw;
  addParseIssue(issues, field, raw);
  return fallback;
}

int readInt(Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is int) return raw;
  addParseIssue(issues, field, raw);
  return 0;
}

bool readBool(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is bool) return raw;
  addParseIssue(issues, field, raw);
  return false;
}

List<String> readStringList(
    Object? raw, String field, List<ParseIssue> issues) {
  if (raw is! List ||
      raw.any((item) => item is! String || !isSafePublicText(item))) {
    addParseIssue(issues, field, raw);
    return const [];
  }
  return List<String>.unmodifiable(raw);
}

enum ReceiptState {
  missing,
  presentUnchecked,
  match,
  drift,
  tampered,
  unverifiable,
  invalidResponse,
}

ReceiptState parseReceiptState(
    Object? raw, String field, List<ParseIssue> issues) {
  const values = {
    'missing': ReceiptState.missing,
    'present_unchecked': ReceiptState.presentUnchecked,
    'MATCH': ReceiptState.match,
    'DRIFT': ReceiptState.drift,
    'TAMPERED': ReceiptState.tampered,
    'UNVERIFIABLE': ReceiptState.unverifiable,
  };
  final parsed = values[raw];
  if (parsed != null) return parsed;
  addParseIssue(issues, field, raw);
  return ReceiptState.invalidResponse;
}

enum EvidenceVerdict { pass, fail, undecided, unverifiable, invalidResponse }

EvidenceVerdict parseEvidenceVerdict(
    Object? raw, String field, List<ParseIssue> issues) {
  const values = {
    'PASS': EvidenceVerdict.pass,
    'FAIL': EvidenceVerdict.fail,
    'UNDECIDED': EvidenceVerdict.undecided,
    'UNVERIFIABLE': EvidenceVerdict.unverifiable,
  };
  final parsed = values[raw];
  if (parsed != null) return parsed;
  addParseIssue(issues, field, raw);
  return EvidenceVerdict.invalidResponse;
}

class JourneyCheck extends DefensiveModel {
  final String checkId, claimId, doesNotProve;
  final String? rawVerdict, rawReceiptState;
  final EvidenceVerdict verdict;
  final List<String> receiptRefs;
  final ReceiptState receiptState;
  final int numerator, denominator;
  const JourneyCheck({
    required this.checkId,
    required this.claimId,
    required this.verdict,
    required this.rawVerdict,
    required this.receiptRefs,
    required this.receiptState,
    required this.rawReceiptState,
    required this.numerator,
    required this.denominator,
    required this.doesNotProve,
    required List<ParseIssue> parseIssues,
  }) : super(parseIssues);
  factory JourneyCheck.fromJson(Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    final verdictField = '$field.verdict';
    final receiptField = '$field.receipt_state';
    final numerator = readInt(json, 'numerator', issues);
    final denominator = readInt(json, 'denominator', issues);
    if (numerator < 0 || denominator < numerator) {
      addParseIssue(issues, '$field.denominator', json['denominator']);
    }
    return JourneyCheck(
      checkId: readText(json, 'check_id', issues),
      claimId: readText(json, 'claim_id', issues),
      verdict: parseEvidenceVerdict(json['verdict'], verdictField, issues),
      rawVerdict: safeRawValue(json['verdict']),
      receiptRefs:
          readStringList(json['receipt_refs'], '$field.receipt_refs', issues),
      receiptState:
          parseReceiptState(json['receipt_state'], receiptField, issues),
      rawReceiptState: safeRawValue(json['receipt_state']),
      numerator: numerator,
      denominator: denominator,
      doesNotProve: readText(json, 'does_not_prove', issues),
      parseIssues: List.unmodifiable(issues),
    );
  }
  bool sameEvidenceAs(JourneyCheck other) =>
      !invalidResponse &&
      !other.invalidResponse &&
      checkId == other.checkId &&
      claimId == other.claimId &&
      rawVerdict == other.rawVerdict &&
      sameList(receiptRefs, other.receiptRefs, (a, b) => a == b) &&
      rawReceiptState == other.rawReceiptState &&
      numerator == other.numerator &&
      denominator == other.denominator &&
      doesNotProve == other.doesNotProve;
}

class JourneyMissingEvidence extends DefensiveModel {
  final String kind, id;
  final List<String> receiptRefs;
  const JourneyMissingEvidence(
      {required this.kind,
      required this.id,
      required this.receiptRefs,
      required List<ParseIssue> parseIssues})
      : super(parseIssues);
  factory JourneyMissingEvidence.fromJson(
      Map<String, Object?> json, String field) {
    final issues = <ParseIssue>[];
    return JourneyMissingEvidence(
      kind: readText(json, 'kind', issues),
      id: readText(json, 'id', issues),
      receiptRefs:
          readStringList(json['receipt_refs'], '$field.receipt_refs', issues),
      parseIssues: List.unmodifiable(issues),
    );
  }
  bool sameEvidenceAs(JourneyMissingEvidence other) =>
      !invalidResponse &&
      !other.invalidResponse &&
      kind == other.kind &&
      id == other.id &&
      sameList(receiptRefs, other.receiptRefs, (a, b) => a == b);
}

class GrantProposal extends DefensiveModel {
  final String proposalRef, plannedGrantRef, action, operationSha256, expiresAt;
  final String? operationRef;
  const GrantProposal(
      this.proposalRef,
      this.plannedGrantRef,
      this.action,
      this.operationSha256,
      this.expiresAt,
      this.operationRef,
      List<ParseIssue> parseIssues)
      : super(parseIssues);
  factory GrantProposal.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.grant-proposal/v1', issues);
    final operation = readText(json, 'operation_ref', issues,
        optional: true, pattern: operationRefPattern);
    return GrantProposal(
        readText(json, 'proposal_ref', issues, pattern: proposalRefPattern),
        readText(json, 'planned_grant_ref', issues, pattern: grantRefPattern),
        readText(json, 'action', issues),
        readText(json, 'operation_sha256', issues, pattern: sha256Pattern),
        readText(json, 'expires_at', issues),
        operation.isEmpty ? null : operation,
        List.unmodifiable(issues));
  }
}

class GrantRef extends DefensiveModel {
  final String grantRef, expiresAt;
  const GrantRef(this.grantRef, this.expiresAt, List<ParseIssue> parseIssues)
      : super(parseIssues);
  factory GrantRef.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.operation-grant-approval/v1', issues);
    return GrantRef(
        readText(json, 'grant_ref', issues, pattern: grantRefPattern),
        readText(json, 'expires_at', issues),
        List.unmodifiable(issues));
  }
}

class JourneyFailure extends DefensiveModel {
  final String code, detail;
  const JourneyFailure(this.code, this.detail, List<ParseIssue> parseIssues)
      : super(parseIssues);
  factory JourneyFailure.fromJson(Map<String, Object?> json) {
    final issues = <ParseIssue>[];
    expectSchema(json, 'flywheel.evidence-transport-error/v1', issues);
    final raw = json['error'];
    if (raw is! Map<String, Object?>) {
      addParseIssue(issues, 'error', raw);
      return JourneyFailure(
          '', 'Response detail unavailable', List.unmodifiable(issues));
    }
    return JourneyFailure(
        readText(raw, 'code', issues),
        readDetail(raw, 'message', issues,
            fallback: 'Response detail unavailable'),
        List.unmodifiable(issues));
  }
}
