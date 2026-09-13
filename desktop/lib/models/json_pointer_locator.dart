import 'dart:convert';
import 'dart:typed_data';

part 'json_pointer_source_index.dart';

const int _maxJsonPointerDepth = 64;

class JsonPointerLocation {
  final String pointer;
  final String _source;
  final int offset, endOffset, line, column;
  final int _start, _end;

  const JsonPointerLocation({
    required this.pointer,
    required this.offset,
    required this.endOffset,
    required this.line,
    required this.column,
    required String source,
    required int start,
    required int end,
  })  : _source = source,
        _start = start,
        _end = end;

  String get context => _source.substring(_start, _end);
  String get label => 'line $line, column $column, offset $offset';
}

class JsonPointerScanException implements FormatException {
  final String code;
  @override
  final String message;
  @override
  final dynamic source;
  @override
  final int? offset;

  const JsonPointerScanException(
    this.code,
    this.message, [
    this.source,
    this.offset,
  ]);

  @override
  String toString() => '$code: $message';
}

class JsonPointerScan {
  final String sourceText;
  final Map<String, JsonPointerLocation> locations;
  const JsonPointerScan(this.sourceText, this.locations);
}

JsonPointerScan scanJsonPointers(Uint8List bytes) {
  final text = utf8.decode(bytes);
  final scanner = _JsonPointerScanner(text);
  scanner.parse();
  return JsonPointerScan(text, Map.unmodifiable(scanner.locations));
}

Map<String, JsonPointerLocation> locateJsonPointers(Uint8List bytes) {
  try {
    return scanJsonPointers(bytes).locations;
  } on Object {
    return const {};
  }
}

String _escapePointerToken(String token) =>
    token.replaceAll('~', '~0').replaceAll('/', '~1');

class _JsonPointerScanner {
  _JsonPointerScanner(this.text)
      : _byteOffsets = _buildByteOffsets(text),
        _lineStarts = _buildLineStarts(text);

  final String text;
  final List<int> _byteOffsets;
  final List<int> _lineStarts;
  final locations = <String, JsonPointerLocation>{};
  int i = 0;

  void parse() {
    _parseValue('', 0);
    _ws();
    if (i != text.length) _error('trailing json');
  }

  void _parseValue(String pointer, int depth) {
    if (depth > _maxJsonPointerDepth) {
      throw JsonPointerScanException(
        'JSON_DEPTH_LIMIT',
        'JSON nesting exceeds $_maxJsonPointerDepth levels.',
        text,
        i,
      );
    }
    _ws();
    final start = i;
    if (i >= text.length) _error('json ended');
    final char = text.codeUnitAt(i);
    if (char == 0x7b) {
      _object(pointer, start, depth);
    } else if (char == 0x5b) {
      _array(pointer, start, depth);
    } else if (char == 0x22) {
      _string();
      _record(pointer, start, i);
    } else {
      _atom();
      _record(pointer, start, i);
    }
  }

  void _object(String pointer, int start, int depth) {
    final seen = <String>{};
    i++;
    _ws();
    if (_take(0x7d)) {
      _record(pointer, start, i);
      return;
    }
    while (true) {
      _ws();
      if (i >= text.length || text.codeUnitAt(i) != 0x22) {
        _error('object key expected');
      }
      final key = _string();
      if (!seen.add(key)) {
        throw JsonPointerScanException(
          'DUPLICATE_KEYS',
          'JSON object contains a duplicate key: $key',
          text,
          i,
        );
      }
      _ws();
      if (!_take(0x3a)) _error('colon expected');
      _parseValue('$pointer/${_escapePointerToken(key)}', depth + 1);
      _ws();
      if (_take(0x7d)) {
        _record(pointer, start, i);
        return;
      }
      if (!_take(0x2c)) _error('comma expected');
    }
  }

  void _array(String pointer, int start, int depth) {
    i++;
    var index = 0;
    _ws();
    if (_take(0x5d)) {
      _record(pointer, start, i);
      return;
    }
    while (true) {
      _parseValue('$pointer/$index', depth + 1);
      index++;
      _ws();
      if (_take(0x5d)) {
        _record(pointer, start, i);
        return;
      }
      if (!_take(0x2c)) _error('comma expected');
    }
  }

  String _string() {
    final out = StringBuffer();
    if (!_take(0x22)) _error('string expected');
    while (i < text.length) {
      final char = text.codeUnitAt(i++);
      if (char == 0x22) return out.toString();
      if (char != 0x5c) {
        out.writeCharCode(char);
        continue;
      }
      if (i >= text.length) _error('bad escape');
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
          if (i + 4 > text.length) _error('bad unicode');
          final hex = text.substring(i, i + 4);
          final code = int.parse(hex, radix: 16);
          out.writeCharCode(code);
          i += 4;
          break;
        default:
          _error('bad escape');
      }
    }
    _error('unterminated string');
  }

  void _atom() {
    final start = i;
    while (i < text.length) {
      final c = text.codeUnitAt(i);
      if (c == 0x2c || c == 0x7d || c == 0x5d || c <= 0x20) break;
      i++;
    }
    if (i == start) _error('atom expected');
  }

  bool _take(int char) {
    if (i < text.length && text.codeUnitAt(i) == char) {
      i++;
      return true;
    }
    return false;
  }

  void _ws() {
    while (i < text.length && text.codeUnitAt(i) <= 0x20) {
      i++;
    }
  }

  Never _error(String message) => throw JsonPointerScanException(
        'INVALID_JSON',
        message,
        text,
        i,
      );

  void _record(String pointer, int start, int end) {
    final lineIndex = _lineIndex(start);
    locations[pointer] = JsonPointerLocation(
      pointer: pointer,
      offset: _byteOffsets[start],
      endOffset: _byteOffsets[end],
      line: lineIndex + 1,
      column: start - _lineStarts[lineIndex] + 1,
      source: text,
      start: start,
      end: end,
    );
  }

  int _lineIndex(int position) {
    var low = 0;
    var high = _lineStarts.length - 1;
    while (low <= high) {
      final mid = low + ((high - low) >> 1);
      if (_lineStarts[mid] <= position) {
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }
    return high < 0 ? 0 : high;
  }
}
