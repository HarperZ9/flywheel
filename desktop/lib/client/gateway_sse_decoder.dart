import 'dart:async';
import 'dart:convert';

final class GatewaySseException implements Exception {
  final String code;
  const GatewaySseException([this.code = 'INVALID_RESPONSE']);
  @override
  String toString() => 'GatewaySseException: $code';
}

final class GatewaySseEvent {
  final int id;
  final String event;
  final Object? data;
  const GatewaySseEvent(this.id, this.event, this.data);
  bool get isDone => event == 'done';
}

final class GatewaySseDecoder
    extends StreamTransformerBase<List<int>, GatewaySseEvent> {
  final int lineLimit, eventLimit, bufferLimit;
  final bool requireIds, requireTerminal;
  const GatewaySseDecoder({
    this.lineLimit = 262144,
    this.eventLimit = 1048576,
    this.bufferLimit = 1048576,
    this.requireIds = true,
    this.requireTerminal = true,
  });

  @override
  Stream<GatewaySseEvent> bind(Stream<List<int>> stream) async* {
    final parser = _SseParser(this);
    try {
      await for (final text in stream.transform(const Utf8Decoder())) {
        for (final event in parser.add(text)) {
          yield event;
        }
      }
      for (final event in parser.close()) {
        yield event;
      }
    } on GatewaySseException {
      rethrow;
    } on Object {
      throw const GatewaySseException();
    }
  }
}

final class _SseParser {
  final GatewaySseDecoder limits;
  final List<String> _data = [];
  String _line = '', _event = '';
  int _lineBytes = 0, _eventBytes = 0, _buffered = 0, _lastId = 0;
  int? _id;
  bool _atStart = true, _afterCr = false, _terminal = false, _done = false;

  _SseParser(this.limits);

  List<GatewaySseEvent> add(String text) {
    final events = <GatewaySseEvent>[];
    for (final rune in text.runes) {
      if (_atStart) {
        _atStart = false;
        if (rune == 0xfeff) continue;
      }
      if (_afterCr) {
        _afterCr = false;
        if (rune == 0x0a) continue;
      }
      if (rune == 0x0d || rune == 0x0a) {
        final event = _finishLine();
        if (event != null) events.add(event);
        _afterCr = rune == 0x0d;
        continue;
      }
      if (_done) _fail();
      final value = String.fromCharCode(rune);
      final bytes = utf8.encode(value).length;
      _line += value;
      _lineBytes += bytes;
      _buffered += bytes;
      if (_lineBytes > limits.lineLimit || _buffered > limits.bufferLimit) {
        _fail();
      }
    }
    return events;
  }

  List<GatewaySseEvent> close() {
    final events = <GatewaySseEvent>[];
    if (_line.isNotEmpty) {
      final event = _finishLine();
      if (event != null) events.add(event);
    }
    if (_hasFields) {
      final event = _dispatch();
      if (event != null) events.add(event);
    }
    if (limits.requireTerminal && !_terminal) _fail();
    return events;
  }

  GatewaySseEvent? _finishLine() {
    final line = _line;
    _eventBytes += _lineBytes + 1;
    _buffered++;
    _line = '';
    _lineBytes = 0;
    if (_eventBytes > limits.eventLimit || _buffered > limits.bufferLimit) {
      _fail();
    }
    if (line.isEmpty) return _dispatch();
    if (line.startsWith(':')) return null;
    final colon = line.indexOf(':');
    final field = colon < 0 ? line : line.substring(0, colon);
    var value = colon < 0 ? '' : line.substring(colon + 1);
    if (value.startsWith(' ')) value = value.substring(1);
    switch (field) {
      case 'id':
        if (_id != null || !RegExp(r'^[0-9]+$').hasMatch(value)) _fail();
        _id = int.tryParse(value) ?? _fail();
      case 'event':
        if (_event.isNotEmpty || value.isEmpty) _fail();
        _event = value;
      case 'data':
        _data.add(value);
      default:
        _fail();
    }
    return null;
  }

  GatewaySseEvent? _dispatch() {
    if (!_hasFields) {
      _reset();
      return null;
    }
    if (_data.isEmpty) _fail();
    final sequence = _id ?? (limits.requireIds ? _fail() : _lastId + 1);
    if (sequence <= _lastId) _fail();
    _lastId = sequence;
    final payload = _data.join('\n');
    final type = _event;
    GatewaySseEvent result;
    if (payload == '[DONE]') {
      if ((type.isNotEmpty && type != 'terminal') ||
          (limits.requireTerminal && !_terminal)) {
        _fail();
      }
      _done = true;
      result = GatewaySseEvent(sequence, 'done', null);
    } else {
      if (_terminal ||
          (type.isEmpty && limits.requireIds) ||
          (type.isNotEmpty &&
              !const {'snapshot', 'progress', 'terminal'}.contains(type))) {
        _fail();
      }
      _JsonKeyScanner(payload).scan();
      final decoded = jsonDecode(payload);
      if (decoded is! Map<String, dynamic>) _fail();
      final effective = type.isEmpty ? 'message' : type;
      _terminal = effective == 'terminal';
      result = GatewaySseEvent(sequence, effective, decoded);
    }
    _reset();
    return result;
  }

  bool get _hasFields => _id != null || _event.isNotEmpty || _data.isNotEmpty;

  void _reset() {
    _id = null;
    _event = '';
    _data.clear();
    _eventBytes = 0;
    _buffered = 0;
  }
}

final class _JsonKeyScanner {
  final String source;
  int index = 0;
  _JsonKeyScanner(this.source);

  void scan() {
    _space();
    _value();
    _space();
    if (index != source.length) _fail();
  }

  void _value() {
    _space();
    if (index >= source.length) _fail();
    switch (source.codeUnitAt(index)) {
      case 0x7b:
        _object();
      case 0x5b:
        _array();
      case 0x22:
        _string();
      default:
        _primitive();
    }
  }

  void _object() {
    index++;
    _space();
    final keys = <String>{};
    if (_take(0x7d)) return;
    while (true) {
      if (index >= source.length || source.codeUnitAt(index) != 0x22) _fail();
      final key = _string();
      if (!keys.add(key)) _fail();
      _space();
      _expect(0x3a);
      _value();
      _space();
      if (_take(0x7d)) return;
      _expect(0x2c);
      _space();
    }
  }

  void _array() {
    index++;
    _space();
    if (_take(0x5d)) return;
    while (true) {
      _value();
      _space();
      if (_take(0x5d)) return;
      _expect(0x2c);
      _space();
    }
  }

  String _string() {
    final start = index;
    _expect(0x22);
    while (index < source.length) {
      final code = source.codeUnitAt(index++);
      if (code == 0x22) {
        final value = jsonDecode(source.substring(start, index));
        return value is String ? value : _fail();
      }
      if (code < 0x20) _fail();
      if (code == 0x5c) {
        if (index >= source.length) _fail();
        index++;
      }
    }
    return _fail();
  }

  void _primitive() {
    final start = index;
    while (index < source.length) {
      final code = source.codeUnitAt(index);
      if (code == 0x2c || code == 0x5d || code == 0x7d || _white(code)) break;
      index++;
    }
    if (index == start) _fail();
  }

  bool _take(int code) {
    if (index >= source.length || source.codeUnitAt(index) != code) {
      return false;
    }
    index++;
    return true;
  }

  void _expect(int code) {
    if (!_take(code)) _fail();
  }

  void _space() {
    while (index < source.length && _white(source.codeUnitAt(index))) {
      index++;
    }
  }
}

bool _white(int code) =>
    code == 0x20 || code == 0x09 || code == 0x0a || code == 0x0d;

Never _fail() => throw const GatewaySseException();
