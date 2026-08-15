import 'dart:convert';

const gatewayErrorSchema = 'flywheel.evidence-transport-error/v1';
final _codePattern = RegExp(r'^[A-Z][A-Z0-9_]{0,63}$');
final _legacyStatusPattern = RegExp(r'^gateway returned ([0-9]{3})$');

class GatewayException implements Exception {
  final int? statusCode;
  final String? errorSchema, errorCode;

  GatewayException(String message,
      {int? statusCode, String? errorSchema, String? errorCode})
      : this._(
          statusCode ?? _legacyStatus(message),
          errorSchema == gatewayErrorSchema ? errorSchema : null,
          errorSchema == gatewayErrorSchema && _validCode(errorCode)
              ? errorCode
              : null,
        );

  GatewayException._(this.statusCode, this.errorSchema, this.errorCode);

  factory GatewayException.fromResponse(int statusCode, String completeBody) {
    final metadata = _parseMetadata(completeBody);
    return GatewayException._(statusCode, metadata?.$1, metadata?.$2);
  }

  String get message => statusCode == null
      ? 'gateway request failed'
      : 'gateway returned $statusCode';

  @override
  String toString() => 'GatewayException: $message';
}

int? _legacyStatus(String message) {
  final match = _legacyStatusPattern.firstMatch(message);
  return match == null ? null : int.tryParse(match.group(1)!);
}

bool _validCode(Object? value) =>
    value is String && _codePattern.hasMatch(value);

(String, String)? _parseMetadata(String completeBody) {
  try {
    final value = jsonDecode(completeBody);
    if (value is! Map<String, dynamic> ||
        value.length != 2 ||
        value['schema'] != gatewayErrorSchema) {
      return null;
    }
    final error = value['error'];
    if (error is! Map<String, dynamic> ||
        error.length != 2 ||
        error['message'] is! String ||
        !_validCode(error['code'])) {
      return null;
    }
    return (gatewayErrorSchema, error['code'] as String);
  } on Object {
    return null;
  }
}
