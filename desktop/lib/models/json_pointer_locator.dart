import 'dart:convert';
import 'dart:typed_data';

class JsonPointerLocation {
  final String pointer, context;
  final int offset, endOffset, line, column;
  const JsonPointerLocation({
    required this.pointer,
    required this.offset,
    required this.endOffset,
    required this.line,
    required this.column,
    required this.context,
  });

  String get label => 'line $line, column $column, offset $offset';
}

Map<String, JsonPointerLocation> locateJsonPointers(Uint8List bytes) {
  try {
    final text = utf8.decode(bytes);
    final scanner = _JsonPointerScanner(text);
    scanner.parse();
    return Map.unmodifiable(scanner.locations);
  } on Object {
    return const {};
  }
}

String _escapePointerToken(String token) =>
    token.replaceAll('~', '~0').replaceAll('/', '~1');

class _JsonPointerScanner {
  _JsonPointerScanner(this.text);

  final String text;
  final locations = <String, JsonPointerLocation>{};
  int i = 0;

  void parse() {
    _parseValue('');
    _ws();
    if (i != text.length) throw const FormatException('trailing json');
  }

  void _parseValue(String pointer) {
    _ws();
    final start = i;
    if (i >= text.length) throw const FormatException('json ended');
    final char = text.codeUnitAt(i);
    if (char == 0x7b) {
      _object(pointer, start);
    } else if (char == 0x5b) {
      _array(pointer, start);
    } else if (char == 0x22) {
      _string();
      _record(pointer, start, i);
    } else {
      _atom();
      _record(pointer, start, i);
    }
  }

  void _object(String pointer, int start) {
    i++;
    _ws();
    if (_take(0x7d)) {
      _record(pointer, start, i);
      return;
    }
    while (true) {
      _ws();
      if (i >= text.length || text.codeUnitAt(i) != 0x22) {
        throw const FormatException('object key expected');
      }
      final key = _string();
      _ws();
      if (!_take(0x3a)) throw const FormatException('colon expected');
      _parseValue('$pointer/${_escapePointerToken(key)}');
      _ws();
      if (_take(0x7d)) {
        _record(pointer, start, i);
        return;
      }
      if (!_take(0x2c)) throw const FormatException('comma expected');
    }
  }

  void _array(String pointer, int start) {
    i++;
    var index = 0;
    _ws();
    if (_take(0x5d)) {
      _record(pointer, start, i);
      return;
    }
    while (true) {
      _parseValue('$pointer/$index');
      index++;
      _ws();
      if (_take(0x5d)) {
        _record(pointer, start, i);
        return;
      }
      if (!_take(0x2c)) throw const FormatException('comma expected');
    }
  }

  String _string() {
    final out = StringBuffer();
    if (!_take(0x22)) throw const FormatException('string expected');
    while (i < text.length) {
      final char = text.codeUnitAt(i++);
      if (char == 0x22) return out.toString();
      if (char != 0x5c) {
        out.writeCharCode(char);
        continue;
      }
      if (i >= text.length) throw const FormatException('bad escape');
      final esc = text.codeUnitAt(i++);
      switch (esc) {
        case 0x22:
        case 0x5c:
        case 0x2f:
          out.writeCharCode(esc);
          break;
        case 0x62:
          out.write('\b');
          break;
        case 0x66:
          out.write('\f');
          break;
        case 0x6e:
          out.write('\n');
          break;
        case 0x72:
          out.write('\r');
          break;
        case 0x74:
          out.write('\t');
          break;
        case 0x75:
          if (i + 4 > text.length) throw const FormatException('bad unicode');
          final hex = text.substring(i, i + 4);
          final code = int.parse(hex, radix: 16);
          out.writeCharCode(code);
          i += 4;
          break;
        default:
          throw const FormatException('bad escape');
      }
    }
    throw const FormatException('unterminated string');
  }

  void _atom() {
    final start = i;
    while (i < text.length) {
      final c = text.codeUnitAt(i);
      if (c == 0x2c || c == 0x7d || c == 0x5d || c <= 0x20) break;
      i++;
    }
    if (i == start) throw const FormatException('atom expected');
  }

  bool _take(int char) {
    if (i < text.length && text.codeUnitAt(i) == char) {
      i++;
      return true;
    }
    return false;
  }

  void _ws() {
    while (i < text.length && text.codeUnitAt(i) <= 0x20) i++;
  }

  void _record(String pointer, int start, int end) {
    final prefix = text.substring(0, start);
    final line = '\n'.allMatches(prefix).length + 1;
    final lastNewline = prefix.lastIndexOf('\n');
    final column = start - lastNewline;
    locations[pointer] = JsonPointerLocation(
      pointer: pointer,
      offset: utf8.encode(prefix).length,
      endOffset: utf8.encode(text.substring(0, end)).length,
      line: line,
      column: column,
      context: text.substring(start, end),
    );
  }
}
