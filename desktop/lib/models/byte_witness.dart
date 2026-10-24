// byte_witness.dart -- the offline half of flywheel.byte-witness/v1, on device.
//
// The gateway hands over records, never bytes. This recomputes each record's
// link in pure Dart, checks that the chain holds, and checks the bytes against
// their digests whenever the caller can produce them. It mirrors
// harness/byte_witness_verify.py, and the vectors are shared with
// tests/test_byte_witness_surface.py.
//
// Three words, and they are not interchangeable:
//
//   match         every check that was asked for ran and reproduced
//   tampered      a check ran and the record does not hold
//   unverifiable  nothing could be checked: a malformed record, or bytes
//                 nobody could produce
//
// Reading the third as the second turns an archive nobody can reach into an
// accusation. Reading it as the first turns it into a lie. Nothing here throws:
// hostile input is a named verdict, because a verifier that crashes on a bad
// record has told its caller nothing about the record.
import 'package:crypto/crypto.dart';

import 'canonical_json.dart';

const String kByteWitnessSchema = 'flywheel.byte-witness/v1';
const String kByteWitnessGenesis = '';

// The failure-class names the engine writes. Same spelling on both sides, so a
// support conversation about a red panel and a log line uses one vocabulary.
const String kWitnessMalformed = 'MALFORMED';
const String kWitnessDigestMismatch = 'DIGEST_MISMATCH';
const String kWitnessLengthMismatch = 'LENGTH_MISMATCH';
const String kWitnessSpanOutOfRange = 'SPAN_OUT_OF_RANGE';
const String kWitnessSpanMismatch = 'SPAN_MISMATCH';
const String kWitnessLinkBroken = 'LINK_BROKEN';
const String kWitnessBytesUnavailable = 'BYTES_UNAVAILABLE';

enum ByteWitnessVerdict { match, tampered, unverifiable }

class ByteWitnessResult {
  final ByteWitnessVerdict verdict;
  final String? failureClass;
  final String detail;
  const ByteWitnessResult(this.verdict, this.failureClass, this.detail);
}

String sha256Hex(List<int> data) => sha256.convert(data).toString();

/// True when [value] is a 64-character hex digest, in either case. Mirrors
/// _digest_well_formed in harness/tool_call_receipt.py, which accepts both;
/// digest equality stays exact, so an uppercase digest that is otherwise right
/// is still a mismatch rather than a shape problem.
bool isWitnessDigest(Object? value) {
  if (value is! String || value.length != 64) return false;
  for (final c in value.codeUnits) {
    final hex = (c >= 0x30 && c <= 0x39) ||
        (c >= 0x61 && c <= 0x66) ||
        (c >= 0x41 && c <= 0x46);
    if (!hex) return false;
  }
  return true;
}

bool _isCount(Object? value) => value is int && value >= 0;

/// The link this record's successor must point back at, or null when the
/// record does not canonicalize and therefore has no link at all.
String? byteWitnessLink(Object? record) {
  try {
    return canonicalJsonSha256(record);
  } on CanonicalJsonError {
    return null;
  }
}

String? _spanShape(Object? span) {
  if (span is! Map) return 'a span is an object';
  if (!_isCount(span['start']) || !_isCount(span['end'])) {
    return 'a span is bounded by whole numbers';
  }
  if (!isWitnessDigest(span['sha256'])) {
    return 'a span carries a 64-character digest';
  }
  // Python reads a missing note as empty text and refuses an explicit null,
  // so the two sides disagree about nothing.
  if (span.containsKey('note') && span['note'] is! String) {
    return 'a span note is text';
  }
  return null;
}

/// A named problem with the record's shape, or null. Needs no bytes.
String? byteWitnessShapeProblem(Object? record) {
  if (record is! Map) return 'a witness record is an object';
  if (record['schema'] != kByteWitnessSchema) {
    return 'record schema is not $kByteWitnessSchema';
  }
  final label = record['label'];
  if (label is! String || label.isEmpty) {
    return 'a record names what its bytes are';
  }
  if (!isWitnessDigest(record['sha256'])) {
    return 'a record carries a 64-character digest';
  }
  if (!_isCount(record['length'])) return 'length is a whole number of bytes';
  if (record['observed_at'] is! String) {
    return 'observed_at is text, and may be empty';
  }
  final prev = record['prev'];
  if (prev is! String ||
      (prev != kByteWitnessGenesis && !isWitnessDigest(prev))) {
    return "prev is empty at genesis, or the previous record's link";
  }
  final spans = record['spans'];
  if (spans is! List) return 'spans is a list';
  if (record['context'] is! Map) return 'context is an object';
  for (final span in spans) {
    final problem = _spanShape(span);
    if (problem != null) return problem;
  }
  return null;
}

/// A record refuted by its own fields, with no reference to any bytes.
String? _selfContradiction(Map record) {
  final length = record['length'] as int;
  for (final span in (record['spans'] as List).cast<Map>()) {
    final start = span['start'] as int;
    final end = span['end'] as int;
    if (!(start < end && end <= length)) {
      return 'span [$start, $end) does not fit inside the $length bytes '
          'this record claims';
    }
  }
  return null;
}

ByteWitnessResult _againstBytes(Map record, List<int> data) {
  final length = record['length'] as int;
  if (data.length != length) {
    return ByteWitnessResult(ByteWitnessVerdict.tampered,
        kWitnessLengthMismatch, 'record claims $length bytes, got ${data.length}');
  }
  if (sha256Hex(data) != record['sha256']) {
    return const ByteWitnessResult(ByteWitnessVerdict.tampered,
        kWitnessDigestMismatch,
        'the bytes do not hash to the digest in the record');
  }
  final spans = (record['spans'] as List).cast<Map>();
  for (final span in spans) {
    final start = span['start'] as int;
    final end = span['end'] as int;
    if (sha256Hex(data.sublist(start, end)) != span['sha256']) {
      return ByteWitnessResult(ByteWitnessVerdict.tampered,
          kWitnessSpanMismatch,
          'span [$start, $end) does not hash to the digest recorded for it');
    }
  }
  return ByteWitnessResult(ByteWitnessVerdict.match, null,
      '$length bytes and ${spans.length} spans reproduced');
}

/// Check one record, with its bytes when the caller has them.
///
/// Without bytes the shape and the record's internal consistency are still
/// checked, and the answer is unverifiable rather than match. A record that
/// passed every check available to it has not passed the one that matters.
ByteWitnessResult verifyByteWitness(Object? record, [List<int>? data]) {
  final problem = byteWitnessShapeProblem(record);
  if (problem != null) {
    return ByteWitnessResult(
        ByteWitnessVerdict.unverifiable, kWitnessMalformed, problem);
  }
  final held = record as Map;
  final contradiction = _selfContradiction(held);
  if (contradiction != null) {
    return ByteWitnessResult(
        ByteWitnessVerdict.tampered, kWitnessSpanOutOfRange, contradiction);
  }
  if (data == null) {
    return const ByteWitnessResult(
        ByteWitnessVerdict.unverifiable,
        kWitnessBytesUnavailable,
        'the record is well formed and self-consistent; nothing checked the '
        'bytes, because none were supplied');
  }
  return _againstBytes(held, data);
}

/// What a byte witness covers. Never empty, whatever the arguments say.
/// Mirrors harness/byte_witness.py `scope()`.
List<String> byteWitnessScope({bool signed = false, bool anchored = false}) {
  return [
    'the digest records that these bytes are unchanged since they were '
        'witnessed; whether they are true, correct or complete is a separate '
        'check',
    'the chain fixes the order and integrity of the records it holds; a '
        'step that was never recorded leaves no link to check',
    'a span records that this byte range hashes to the recorded digest; '
        "whether the range fits the claim it backs is the citer's call",
    if (signed)
      'the signature binds this record to its key; who holds that key, and '
          'whether the bytes came from their source, rest on other evidence'
    else
      'the chain is unsigned; its links detect accidental change, and a '
          'writer who can rewrite a record can recompute every later link',
    if (anchored)
      'the anchor dates the chain as existing by the anchored head; single '
          'records inside it share that one bound'
    else
      "observed_at is the caller's own note, unchecked by any clock here; an "
          'external anchor is what dates a chain',
  ];
}
