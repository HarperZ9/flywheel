// byte_witness_chain.dart -- check that a run's records form one chain.
//
// One record proves its own bytes. A chain proves the order they were witnessed
// in, so a record inserted after the fact has to forge every link that follows
// it. This mirrors verify_chain in harness/byte_witness_verify.py, including the
// part that is easy to get wrong: a broken link is tampered, not unverifiable.
// The words name the record and not an intent. Whether a link broke through
// malice or through misassembly, the chain in hand does not hold, and it was
// checkable enough to say so.
//
// `start` is what the first record must point back at, and it defaults to
// genesis, so a segment lifted out of a longer chain reads as unverifiable
// rather than quietly matching. A caller holding the earlier head passes it in.
import 'dart:convert';

import 'byte_witness.dart';

class ByteWitnessChainResult {
  final ByteWitnessVerdict verdict;
  final String? failureClass;

  /// The index of the record the chain failed at, or null when it failed as a
  /// whole. Not a count: record 0 can be the broken one.
  final int? brokenAt;

  /// The link the last checked record produced. Bind it somewhere a change to
  /// the chain cannot follow it, or nothing checks the newest record.
  final String? head;
  final int checked;
  final String detail;
  final List<String> doesNotProve;
  const ByteWitnessChainResult({
    required this.verdict,
    required this.failureClass,
    required this.brokenAt,
    required this.head,
    required this.checked,
    required this.detail,
    required this.doesNotProve,
  });
}

/// Hands back the bytes behind a digest, or null when it does not hold them.
typedef ByteResolver = List<int>? Function(String sha256);

ByteWitnessChainResult _chainResult(ByteWitnessVerdict verdict,
    String? failureClass, int? brokenAt, String? head, int checked,
    String detail) {
  return ByteWitnessChainResult(
    verdict: verdict,
    failureClass: failureClass,
    brokenAt: brokenAt,
    head: head,
    checked: checked,
    detail: detail,
    doesNotProve: byteWitnessDoesNotProve()
      ..add('the last record is checked by nothing after it, so bind the head '
          'somewhere a change to the chain cannot follow it'),
  );
}

/// A resolver that throws is a resolver that failed, not a tampered record.
List<int>? _resolved(ByteResolver? resolve, Object? record) {
  if (resolve == null || record is! Map) return null;
  final digest = record['sha256'];
  if (digest is! String) return null;
  try {
    return resolve(digest);
  } catch (_) {
    return null;
  }
}

/// Check that records form one chain, and their bytes when a resolver is given.
///
/// Never throws. Every way this can fail is a named verdict.
ByteWitnessChainResult verifyByteWitnessChain(
  Object? records, {
  String start = kByteWitnessGenesis,
  ByteResolver? resolve,
}) {
  if (records is! List || records.isEmpty) {
    return _chainResult(ByteWitnessVerdict.unverifiable, kWitnessMalformed,
        null, null, 0, 'there is no chain here to check');
  }
  if (start != kByteWitnessGenesis && !isWitnessDigest(start)) {
    return _chainResult(ByteWitnessVerdict.unverifiable, kWitnessMalformed,
        null, null, 0, 'start is empty at genesis, or a 64-character link');
  }
  var expected = start;
  String? head;
  var unresolved = 0;
  for (var index = 0; index < records.length; index++) {
    final record = records[index];
    final one = verifyByteWitness(record, _resolved(resolve, record));
    if (one.verdict == ByteWitnessVerdict.tampered) {
      return _chainResult(ByteWitnessVerdict.tampered, one.failureClass, index,
          head, index, one.detail);
    }
    if (one.failureClass == kWitnessMalformed) {
      return _chainResult(ByteWitnessVerdict.unverifiable, kWitnessMalformed,
          index, head, index, 'record $index: ${one.detail}');
    }
    if (one.failureClass == kWitnessBytesUnavailable) {
      // The link is still checked below. A resolver was asked for these bytes
      // and could not produce them, so the chain is linked but not fully
      // reproduced, and match would overstate what ran.
      unresolved++;
    }
    final prev = (record as Map)['prev'] as String;
    if (prev != expected) {
      return _chainResult(
          ByteWitnessVerdict.tampered,
          kWitnessLinkBroken,
          index,
          head,
          index,
          'record $index points back at ${prev.isEmpty ? 'genesis' : prev}, '
          'and the record before it links to '
          '${expected.isEmpty ? 'genesis' : expected}');
    }
    head = byteWitnessLink(record);
    if (head == null) {
      return _chainResult(ByteWitnessVerdict.unverifiable, kWitnessMalformed,
          index, null, index,
          'record $index does not canonicalize, so it has no link');
    }
    expected = head;
  }
  if (resolve == null) {
    return _chainResult(
        ByteWitnessVerdict.unverifiable,
        kWitnessBytesUnavailable,
        null,
        head,
        records.length,
        '${records.length} records link into one chain; no resolver was '
        'given, so no bytes were checked');
  }
  if (unresolved > 0) {
    return _chainResult(
        ByteWitnessVerdict.unverifiable,
        kWitnessBytesUnavailable,
        null,
        head,
        records.length,
        '${records.length} records link into one chain; $unresolved could not '
        'be resolved to bytes, so the chain is linked but not fully '
        'reproduced');
  }
  return _chainResult(ByteWitnessVerdict.match, null, null, head,
      records.length,
      '${records.length} records link into one chain and every witnessed byte '
      'sequence reproduced');
}

/// Read a witness log the way it actually arrives: a JSON array, one JSON
/// object per line, or a whole run result with the chain nested inside it.
///
/// Returns null when nothing in the text reads as records. That is a parse
/// failure and not a verdict about anyone's bytes, so the caller says so in
/// those words rather than rendering a chain nobody handed it.
List<dynamic>? readByteWitnessLog(String text) {
  final trimmed = text.trim();
  if (trimmed.isEmpty) return null;
  try {
    final decoded = jsonDecode(trimmed);
    if (decoded is List) return decoded;
    if (decoded is Map) {
      final nested = decoded['action_witness'];
      if (nested is Map && nested['records'] is List) {
        return nested['records'] as List;
      }
      if (decoded['records'] is List) return decoded['records'] as List;
      if (decoded['schema'] == kByteWitnessSchema) return [decoded];
    }
    return null;
  } on FormatException {
    // Not one document. The engine writes one record per line.
    final records = <dynamic>[];
    for (final line in const LineSplitter().convert(trimmed)) {
      if (line.trim().isEmpty) continue;
      try {
        records.add(jsonDecode(line));
      } on FormatException {
        return null;
      }
    }
    return records.isEmpty ? null : records;
  }
}
