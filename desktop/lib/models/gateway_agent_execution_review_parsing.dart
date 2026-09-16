part of 'gateway_agent_execution_review.dart';

String _readChoice(Map<String, Object?> json, String field, Set<String> allowed,
    List<ParseIssue> issues,
    {bool optional = false}) {
  final raw = json[field];
  if (optional && raw == null) return '';
  if (raw is String && allowed.contains(raw)) return raw;
  addParseIssue(issues, field, raw);
  return '';
}

String _readModelReference(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is String &&
      raw.isNotEmpty &&
      _modelReference.hasMatch(raw) &&
      isSafePublicText(raw)) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return '';
}

String? _readNullableModelReference(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw == null) return null;
  if (raw is String &&
      raw.isNotEmpty &&
      _modelReference.hasMatch(raw) &&
      isSafePublicText(raw)) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return null;
}

String? _readNullableText(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw == null) return null;
  if (raw is String && raw.isNotEmpty && isSafePublicText(raw)) return raw;
  addParseIssue(issues, field, raw);
  return null;
}

String? _readNullableSha256(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw == null) return null;
  if (raw is String && sha256Pattern.hasMatch(raw)) return raw;
  addParseIssue(issues, field, raw);
  return null;
}

List<String> _readToolNames(
    Object? raw, String field, List<ParseIssue> issues) {
  final values = readStringList(raw, field, issues);
  if (values.any((value) => !_toolName.hasMatch(value)) ||
      values.toSet().length != values.length) {
    addParseIssue(issues, field, raw);
    return const [];
  }
  return values;
}

String _readEndpointBaseUrl(
    Map<String, Object?> json, String field, List<ParseIssue> issues,
    {bool allowEmpty = false}) {
  final raw = json[field];
  if (allowEmpty) {
    if (raw == '') return '';
    addParseIssue(issues, field, raw);
    return '';
  }
  final parsed = raw is String ? Uri.tryParse(raw) : null;
  if (raw is String &&
      raw.isNotEmpty &&
      raw.length <= 512 &&
      !_endpointSecret.hasMatch(raw) &&
      !_endpointAssignedSecret.hasMatch(raw) &&
      !raw.contains('\\') &&
      !raw.codeUnits.any((unit) => unit <= 0x20 || unit == 0x7f) &&
      parsed != null &&
      const {'http', 'https'}.contains(parsed.scheme) &&
      parsed.hasAuthority &&
      parsed.userInfo.isEmpty &&
      !parsed.hasQuery &&
      !parsed.hasFragment) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return '';
}

String _readLocalPath(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is String &&
      raw.isNotEmpty &&
      raw.length <= 512 &&
      !_isUriShapedPath(raw) &&
      _isAbsoluteLocalPath(raw) &&
      !raw.codeUnits.any((unit) => unit <= 0x1f || unit == 0x7f) &&
      isSafeLocalPath(raw)) {
    return raw;
  }
  addParseIssue(issues, field, raw);
  return '';
}

bool _isAbsoluteLocalPath(String value) =>
    _windowsAbsolutePath.hasMatch(value) ||
    _posixAbsolutePath.hasMatch(value) ||
    _uncAbsolutePath.hasMatch(value);

bool _isUriShapedPath(String value) =>
    _uriScheme.hasMatch(value) && !_windowsAbsolutePath.hasMatch(value);

int _readInt(Map<String, Object?> json, String field, int min, int max,
    List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is int && raw >= min && raw <= max) return raw;
  addParseIssue(issues, field, raw);
  return 0;
}

bool _readBool(
    Map<String, Object?> json, String field, List<ParseIssue> issues) {
  final raw = json[field];
  if (raw is bool) return raw;
  addParseIssue(issues, field, raw);
  return false;
}

void _exactFields(Map<String, Object?> value, Set<String> fields,
    List<ParseIssue> issues, String field) {
  if (value.keys.toSet().length != fields.length ||
      !value.keys.every(fields.contains)) {
    addParseIssue(issues, field, value.keys.toList());
  }
}
