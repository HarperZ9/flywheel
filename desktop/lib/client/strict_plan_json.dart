import 'dart:convert';

Map<String, dynamic> strictPlanJsonObject(List<int> raw) {
  try {
    if (raw.length > 1048576) throw const FormatException();
    final text = utf8.decode(raw, allowMalformed: false);
    _PlanJsonScanner(text).scan();
    final value = jsonDecode(text);
    if (value is! Map<String, dynamic>) throw const FormatException();
    return value;
  } on FormatException {
    rethrow;
  } on Object {
    throw const FormatException('Invalid Plan JSON');
  }
}

final class _PlanJsonScanner {
  final String source;
  int index = 0;
  int nodes = 0;
  _PlanJsonScanner(this.source);

  Never _invalid() => throw const FormatException('Invalid Plan JSON');
  bool _at(String value) =>
      index < source.length && source.codeUnitAt(index) == value.codeUnitAt(0);
  void _space() {
    while (index < source.length &&
        const {0x20, 0x09, 0x0a, 0x0d}.contains(source.codeUnitAt(index))) {
      index++;
    }
  }

  void scan() {
    _space();
    if (!_at('{')) _invalid();
    _value(0);
    _space();
    if (index != source.length) _invalid();
  }

  void _value(int depth) {
    if (depth > 16 || ++nodes > 4096 || index >= source.length) _invalid();
    final unit = source.codeUnitAt(index);
    if (unit == 0x7b) return _object(depth);
    if (unit == 0x5b) return _array(depth);
    if (unit == 0x22) {
      _string();
      return;
    }
    if (unit == 0x2d || unit >= 0x30 && unit <= 0x39) return _number();
    if (_literal('true') || _literal('false') || _literal('null')) return;
    _invalid();
  }

  void _object(int depth) {
    index++;
    _space();
    final keys = <String>{};
    if (_at('}')) {
      index++;
      return;
    }
    while (true) {
      if (!_at('"') || !keys.add(_string())) _invalid();
      _space();
      if (!_at(':')) _invalid();
      index++;
      _space();
      _value(depth + 1);
      _space();
      if (_at('}')) {
        index++;
        return;
      }
      if (!_at(',')) _invalid();
      index++;
      _space();
    }
  }

  void _array(int depth) {
    index++;
    _space();
    if (_at(']')) {
      index++;
      return;
    }
    while (true) {
      _value(depth + 1);
      _space();
      if (_at(']')) {
        index++;
        return;
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

  void _number() {
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
  }

  bool _literal(String value) {
    if (!source.startsWith(value, index)) return false;
    index += value.length;
    return true;
  }

  bool _digit(int unit) => unit >= 0x30 && unit <= 0x39;
  bool _nonzero(int unit) => unit >= 0x31 && unit <= 0x39;
}
