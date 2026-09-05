// canonical_json.dart -- the one byte encoding both halves of Flywheel agree on.
//
// harness/evidence_json.py canonicalizes with
//   json.dumps(value, sort_keys=True, separators=(",", ":"),
//              ensure_ascii=False, allow_nan=False).encode("utf-8", "strict")
// and every link in a byte-witness chain is a sha256 over exactly those bytes.
// A re-encoder that disagrees anywhere recomputes a different link, and the
// record after it then reads as broken. That is a false accusation, which is
// the one failure a verifier must never produce. So this refuses whatever it
// cannot reproduce byte for byte instead of guessing at it.
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// A value this encoder will not spell, because the two runtimes disagree.
class CanonicalJsonError implements Exception {
  final String message;
  const CanonicalJsonError(this.message);
  @override
  String toString() => message;
}

const int _maxDepth = 64;

/// Order two keys the way Python's `sort_keys=True` orders them: by Unicode
/// code point. Dart's own `compareTo` orders by UTF-16 code unit, which puts
/// every astral character before U+E000..U+FFFF and would sort a record's keys
/// into an order Python never wrote.
int compareByCodePoint(String a, String b) {
  final x = a.runes.toList();
  final y = b.runes.toList();
  final shared = x.length < y.length ? x.length : y.length;
  for (var i = 0; i < shared; i++) {
    if (x[i] != y[i]) return x[i] < y[i] ? -1 : 1;
  }
  return x.length - y.length;
}

/// The canonical bytes of a JSON value. Throws [CanonicalJsonError] on anything
/// outside the data model, or outside what this can reproduce exactly.
Uint8List canonicalJsonBytes(Object? value) {
  final out = StringBuffer();
  _write(out, value, 0);
  return Uint8List.fromList(utf8.encode(out.toString()));
}

/// The lowercase hex sha256 of [canonicalJsonBytes]. This is a witness link.
String canonicalJsonSha256(Object? value) =>
    sha256.convert(canonicalJsonBytes(value)).toString();

void _write(StringBuffer out, Object? value, int depth) {
  if (depth > _maxDepth) {
    throw const CanonicalJsonError('the value nests too deeply to canonicalize');
  }
  if (value == null) {
    out.write('null');
  } else if (value is bool) {
    out.write(value ? 'true' : 'false');
  } else if (value is int) {
    out.write(value.toString());
  } else if (value is double) {
    // Dart writes 1e-7 where Python writes 1e-07, and 1 where Python writes
    // 1.0. No harness record carries a float, so refusing costs nothing real
    // and keeps a guess from ever becoming a link.
    throw const CanonicalJsonError(
        'a fractional number has no spelling both runtimes agree on');
  } else if (value is String) {
    _writeString(out, value);
  } else if (value is List) {
    out.write('[');
    for (var i = 0; i < value.length; i++) {
      if (i > 0) out.write(',');
      _write(out, value[i], depth + 1);
    }
    out.write(']');
  } else if (value is Map) {
    _writeMap(out, value, depth);
  } else {
    throw CanonicalJsonError(
        '${value.runtimeType} is outside the JSON data model');
  }
}

void _writeMap(StringBuffer out, Map<Object?, Object?> value, int depth) {
  final keys = <String>[];
  for (final key in value.keys) {
    if (key is! String) {
      throw const CanonicalJsonError('an object key is text');
    }
    keys.add(key);
  }
  keys.sort(compareByCodePoint);
  out.write('{');
  for (var i = 0; i < keys.length; i++) {
    if (i > 0) out.write(',');
    _writeString(out, keys[i]);
    out.write(':');
    _write(out, value[keys[i]], depth + 1);
  }
  out.write('}');
}

void _writeString(StringBuffer out, String value) {
  out.write('"');
  for (var i = 0; i < value.length; i++) {
    final unit = value.codeUnitAt(i);
    if (unit == 0x22) {
      out.write(r'\"');
    } else if (unit == 0x5c) {
      out.write(r'\');
    } else if (unit < 0x20) {
      out.write(_control(unit));
    } else if (unit >= 0xd800 && unit <= 0xdfff) {
      // An unpaired surrogate makes Python's strict UTF-8 encode raise, while
      // Dart quietly substitutes U+FFFD. Two different byte strings, one of
      // which does not exist. Neither is an answer.
      final next = i + 1 < value.length ? value.codeUnitAt(i + 1) : 0;
      if (unit > 0xdbff || next < 0xdc00 || next > 0xdfff) {
        throw const CanonicalJsonError(
            'the text carries an unpaired surrogate, which the two runtimes '
            'do not turn into the same bytes');
      }
      out.write(value.substring(i, i + 2));
      i++;
    } else {
      out.writeCharCode(unit);
    }
  }
  out.write('"');
}

String _control(int unit) {
  switch (unit) {
    case 0x08:
      return r'\b';
    case 0x09:
      return r'\t';
    case 0x0a:
      return r'\n';
    case 0x0c:
      return r'\f';
    case 0x0d:
      return r'\r';
  }
  return r'\u' + unit.toRadixString(16).padLeft(4, '0');
}
