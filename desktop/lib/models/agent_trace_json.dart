// Strict bounded private JSON; preserves original canonical bytes separately.
import 'dart:convert';
import 'agent_trace.dart';

Map<String, dynamic> traceJsonObject(List<int> raw,
    {int maxBytes = traceMaxRecordBytes,
    int maxDepth = 32,
    int maxNodes = traceMaxJsonNodes}) {
  try {
    if (raw.length > maxBytes) throw const TraceLimitException();
    final text = utf8.decode(raw, allowMalformed: false);
    return _TraceJsonScanner(text, maxDepth, maxNodes).parse();
  } on TraceLimitException {
    rethrow;
  } on Object {
    throw const FormatException('Private trace JSON is invalid');
  }
}

final class _TraceJsonScanner {
  final String source;
  final int maxDepth;
  final int maxNodes;
  int index = 0;
  int nodes = 0;
  _TraceJsonScanner(this.source, this.maxDepth, this.maxNodes);

  Never _invalid() =>
      throw const FormatException('Private trace JSON is invalid');
  bool _at(String value) =>
      index < source.length && source.codeUnitAt(index) == value.codeUnitAt(0);
  void _space() {
    while (index < source.length &&
        const {0x20, 0x09, 0x0a, 0x0d}.contains(source.codeUnitAt(index))) {
      index++;
    }
  }

  Map<String, dynamic> parse() {
    _space();
    if (!_at('{')) _invalid();
    final value = _value(0);
    _space();
    if (index != source.length) _invalid();
    return value as Map<String, dynamic>;
  }

  Object? _value(int depth) {
    if (++nodes > maxNodes || depth > maxDepth) {
      throw const TraceLimitException();
    }
    if (index >= source.length) {
      _invalid();
    }
    final unit = source.codeUnitAt(index);
    if ((unit == 0x7b || unit == 0x5b) && depth >= maxDepth) {
      throw const TraceLimitException();
    }
    if (unit == 0x7b) return _object(depth);
    if (unit == 0x5b) return _array(depth);
    if (unit == 0x22) return _string();
    if (unit == 0x2d || unit >= 0x30 && unit <= 0x39) return _number();
    if (_literal('true')) return true;
    if (_literal('false')) return false;
    if (_literal('null')) return null;
    _invalid();
  }

  Map<String, dynamic> _object(int depth) {
    index++;
    _space();
    final value = <String, dynamic>{};
    if (_at('}')) {
      index++;
      return value;
    }
    while (true) {
      if (!_at('"')) _invalid();
      final key = _string();
      if (value.containsKey(key)) _invalid();
      _space();
      if (!_at(':')) _invalid();
      index++;
      _space();
      value[key] = _value(depth + 1);
      _space();
      if (_at('}')) {
        index++;
        return value;
      }
      if (!_at(',')) _invalid();
      index++;
      _space();
    }
  }

  List<Object?> _array(int depth) {
    index++;
    _space();
    final value = <Object?>[];
    if (_at(']')) {
      index++;
      return value;
    }
    while (true) {
      value.add(_value(depth + 1));
      _space();
      if (_at(']')) {
        index++;
        return value;
      }
      if (!_at(',')) _invalid();
      index++;
      _space();
    }
  }

  String _string() {
    if (!_at('"')) _invalid();
    index++;
    final decoded = StringBuffer();
    while (index < source.length) {
      var unit = source.codeUnitAt(index++);
      if (unit == 0x22) return decoded.toString();
      if (unit < 0x20) _invalid();
      if (unit == 0x5c) {
        unit = _escape(decoded);
        if (unit < 0) continue;
      }
      if (unit >= 0xd800 && unit <= 0xdbff) {
        if (index >= source.length) _invalid();
        final low = source.codeUnitAt(index++);
        if (low < 0xdc00 || low > 0xdfff) _invalid();
        decoded.writeCharCode(unit);
        decoded.writeCharCode(low);
      } else {
        if (unit >= 0xdc00 && unit <= 0xdfff) _invalid();
        decoded.writeCharCode(unit);
      }
    }
    return _invalid();
  }

  int _escape(StringBuffer decoded) {
    if (index >= source.length) _invalid();
    final escape = source.codeUnitAt(index++);
    const simple = {
      0x22: 0x22,
      0x5c: 0x5c,
      0x2f: 0x2f,
      0x62: 0x08,
      0x66: 0x0c,
      0x6e: 0x0a,
      0x72: 0x0d,
      0x74: 0x09
    };
    if (simple.containsKey(escape)) {
      decoded.writeCharCode(simple[escape]!);
      return -1;
    }
    if (escape != 0x75) _invalid();
    final high = _hex4();
    if (high >= 0xdc00 && high <= 0xdfff) _invalid();
    if (high < 0xd800 || high > 0xdbff) return high;
    if (index + 6 > source.length ||
        source.codeUnitAt(index) != 0x5c ||
        source.codeUnitAt(index + 1) != 0x75) {
      _invalid();
    }
    index += 2;
    final low = _hex4();
    if (low < 0xdc00 || low > 0xdfff) _invalid();
    decoded.writeCharCode(high);
    decoded.writeCharCode(low);
    return -1;
  }

  int _hex4() {
    if (index + 4 > source.length) _invalid();
    var value = 0;
    for (var count = 0; count < 4; count++) {
      final unit = source.codeUnitAt(index++);
      final digit = unit >= 0x30 && unit <= 0x39
          ? unit - 0x30
          : unit >= 0x41 && unit <= 0x46
              ? unit - 0x41 + 10
              : unit >= 0x61 && unit <= 0x66
                  ? unit - 0x61 + 10
                  : -1;
      if (digit < 0) _invalid();
      value = value * 16 + digit;
    }
    return value;
  }

  Object _number() {
    final start = index;
    if (_at('-')) index++;
    if (index >= source.length) _invalid();
    if (_at('0')) {
      index++;
      if (index < source.length && _digit(source.codeUnitAt(index))) _invalid();
    } else {
      if (!_nonzero(source.codeUnitAt(index))) _invalid();
      while (index < source.length && _digit(source.codeUnitAt(index))) {
        index++;
      }
    }
    if (_at('.')) {
      index++;
      if (index >= source.length || !_digit(source.codeUnitAt(index))) {
        _invalid();
      }
      while (index < source.length && _digit(source.codeUnitAt(index))) {
        index++;
      }
    }
    if (_at('e') || _at('E')) {
      index++;
      if (_at('+') || _at('-')) index++;
      if (index >= source.length || !_digit(source.codeUnitAt(index))) {
        _invalid();
      }
      while (index < source.length && _digit(source.codeUnitAt(index))) {
        index++;
      }
    }
    final raw = source.substring(start, index);
    if (raw.contains('.') || raw.contains('e') || raw.contains('E')) {
      final number = double.tryParse(raw);
      if (number == null || !number.isFinite) _invalid();
      return number;
    }
    // Python's JSON domain includes integers larger than Dart's native int.
    // Keep these exact instead of silently converting their recorded value.
    if (raw.length - (raw.startsWith('-') ? 1 : 0) > 4300) {
      throw const TraceLimitException();
    }
    return int.tryParse(raw) ?? BigInt.parse(raw);
  }

  bool _literal(String value) {
    if (!source.startsWith(value, index)) return false;
    index += value.length;
    return true;
  }

  bool _digit(int unit) => unit >= 0x30 && unit <= 0x39;
  bool _nonzero(int unit) => unit >= 0x31 && unit <= 0x39;
}
