part of 'operation_models.dart';

final class OperationResult {
  final String operationRef, action;
  final OperationState state;
  final Map<String, Object?> result;

  const OperationResult._(
    this.operationRef,
    this.action,
    this.state,
    this.result,
  );

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
        !const {'agent.run', 'output.check'}.contains(action) ||
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

  Map<String, Object?> toJson() => {
        'schema': operationResultSchema,
        'operation_ref': operationRef,
        'action': action,
        'state': _wireState(state),
        'result': result,
      };

  String get canonicalSha256 =>
      sha256.convert(utf8.encode(_canonicalJson(toJson()))).toString();
}

String _canonicalJson(Object? value) {
  if (value == null) return 'null';
  if (value is bool || value is int) return value.toString();
  if (value is double) return _pythonDouble(value);
  if (value is String) return jsonEncode(value);
  if (value is List) return '[${value.map(_canonicalJson).join(',')}]';
  if (value is Map) {
    final keys = value.keys.cast<String>().toList()..sort(_unicodeCompare);
    return '{${keys.map((key) => '${jsonEncode(key)}:${_canonicalJson(value[key])}').join(',')}}';
  }
  return _invalid();
}

int _unicodeCompare(String left, String right) {
  final a = utf8.encode(left), b = utf8.encode(right);
  for (var index = 0; index < a.length && index < b.length; index++) {
    if (a[index] != b[index]) return a[index].compareTo(b[index]);
  }
  return a.length.compareTo(b.length);
}

String _pythonDouble(double value) {
  if (!value.isFinite) return _invalid();
  if (value == 0) return value.isNegative ? '-0.0' : '0.0';
  var raw = value.abs().toString().toLowerCase();
  final parts = raw.split('e');
  final exponent = parts.length == 2 ? int.parse(parts[1]) : 0;
  final point = parts[0].indexOf('.');
  var digits = parts[0].replaceAll('.', '');
  var decimal = (point < 0 ? digits.length : point) + exponent;
  while (digits.startsWith('0')) {
    digits = digits.substring(1);
    decimal--;
  }
  while (digits.length > 1 && digits.endsWith('0')) {
    digits = digits.substring(0, digits.length - 1);
  }
  final scientific = decimal - 1;
  if (scientific < -4 || scientific >= 16) {
    final mantissa =
        digits.length == 1 ? digits : '${digits[0]}.${digits.substring(1)}';
    final sign = scientific < 0 ? '-' : '+';
    return '${value.isNegative ? '-' : ''}$mantissa'
        'e$sign${scientific.abs().toString().padLeft(2, '0')}';
  }
  if (decimal <= 0) {
    raw = '0.${'0' * -decimal}$digits';
  } else if (decimal >= digits.length) {
    raw = '$digits${'0' * (decimal - digits.length)}.0';
  } else {
    raw = '${digits.substring(0, decimal)}.${digits.substring(decimal)}';
  }
  return '${value.isNegative ? '-' : ''}$raw';
}
