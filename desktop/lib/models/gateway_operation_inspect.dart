part of 'gateway_grant_models.dart';

String? _inspectSha256(Map<String, Object?> value) {
  final source = value['source'];
  final sha = source is Map ? source['sha256'] : null;
  return sha is String && sha256Pattern.hasMatch(sha) ? sha : null;
}

String _inspectDataRef(String sha) =>
    'data_inspect.source:${sha.substring(0, 32)}';

bool _validInspectFilename(Object? value) {
  if (value == null) return true;
  if (value is! String || value.isEmpty || value.length > 120) return false;
  if (value.contains('/') ||
      value.contains(r'\') ||
      value.contains(':') ||
      value.toLowerCase().startsWith('file:')) {
    return false;
  }
  for (final unit in value.codeUnits) {
    if (unit < 0x20 || unit > 0x7e) return false;
  }
  return isSafePublicText(value);
}

void _validateImportInspect(
  Map<String, Object?> value,
  GatewayDestination destination,
) {
  final source = value['source'];
  final sha = _inspectSha256(value);
  final length = source is Map ? source['byte_length'] : null;
  final refs = value['data_refs'];
  final credentials = value['credential_refs'];
  if (source is! Map ||
      source['kind'] != 'client-upload' ||
      source['format'] != 'inspect-json' ||
      sha == null ||
      length is! int ||
      length < 1 ||
      length > 16777216 ||
      !_validInspectFilename(source['filename']) ||
      refs is! List ||
      refs.length != 1 ||
      refs.single != _inspectDataRef(sha) ||
      credentials is! List ||
      credentials.isNotEmpty ||
      destination.kind != 'import' ||
      destination.ref != 'inspect-json:${sha.substring(0, 16)}') {
    _invalid();
  }
}
