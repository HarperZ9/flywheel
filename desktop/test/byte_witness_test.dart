// The Dart side of the byte-witness/v1 contract: the client recomputes each
// record's link itself and never takes the gateway's word for a chain.
// Vectors are the shared fixtures from tests/test_byte_witness_surface.py,
// which fails if this file and the engine ever drift apart.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/byte_witness.dart';
import 'package:flywheel_desktop/models/byte_witness_chain.dart';
import 'package:flywheel_desktop/models/canonical_json.dart';

const _firstLink =
    'dbe349afee22df36ef03ad06e28f8693b46412c48001e22a1c56567897940be2';
const _secondLink =
    '5d592e36e826fe6f35d25d3627d5ef28f05556dd3408e75866daa6297aa3ce9c';
const _oddLink =
    'a93d25123087175d1c2adac11ac7e9fbf6e558db5d4843e60c65bb2b0ad62fe6';
const _spanSha =
    '22c72aa82ce77c82e2ca65a711c79eaa4b51c57f85f91489ceeacc7b385943ba';

final _firstBytes = utf8.encode('hello world');
final _secondBytes = utf8.encode('the quick brown fox');

Map<String, dynamic> _first() => {
      'context': {'kind': 'input', 'seq': 1},
      'label': 'doc/input',
      'length': 11,
      'observed_at': '',
      'prev': '',
      'schema': kByteWitnessSchema,
      'sha256':
          'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9',
      'spans': <dynamic>[],
    };

Map<String, dynamic> _second() => {
      'context': {'kind': 'output', 'seq': 1},
      'label': 'doc/output',
      'length': 19,
      'observed_at': '',
      'prev': _firstLink,
      'schema': kByteWitnessSchema,
      'sha256':
          '9ecb36561341d18eb65484e833efea61edc74b84cf5e6ae1b81c63533e25fc8f',
      'spans': <dynamic>[
        {'end': 9, 'note': 'verb phrase', 'sha256': _spanSha, 'start': 4},
      ],
    };

// A Latin-1 letter, U+2028, and an astral emoji whose UTF-16 form is a
// surrogate pair, with a context value carrying a tab and a newline.
Map<String, dynamic> _odd() => {
      'context': {'n': 7, 'note': 'tab\there\nnewline', 'ok': true},
      'label': 'odd/\u00e9\u2028\u{1F600}',
      'length': 2,
      'observed_at': '',
      'prev': '',
      'schema': kByteWitnessSchema,
      'sha256':
          'b413f47d13ee2fe6c845b2ee141af81de858df4ec549a58b7970bb96645bc8d2',
      'spans': <dynamic>[],
    };

ByteResolver _store() {
  final held = {
    _first()['sha256'] as String: _firstBytes,
    _second()['sha256'] as String: _secondBytes,
  };
  return (digest) => held[digest];
}

void main() {
  group('canonical encoding', () {
    test('recomputes the links the engine wrote', () {
      expect(byteWitnessLink(_first()), _firstLink);
      expect(byteWitnessLink(_second()), _secondLink);
    });

    test('survives text a naive re-encoder gets wrong', () {
      expect(byteWitnessLink(_odd()), _oddLink);
    });

    test('orders keys by code point, not by UTF-16 code unit', () {
      // Dart's String.compareTo works in UTF-16, where an astral key starts
      // with a surrogate at U+D800 and sorts before U+FFFD. Python sorts by
      // code point, where U+FFFD comes first. This is that disagreement.
      final text = utf8.decode(
          canonicalJsonBytes({'\u{10000}': 1, '\uFFFD': 2}));
      expect(text.indexOf('\uFFFD'),
          lessThan(text.indexOf('\u{10000}')));
    });

    test('refuses a fractional number rather than guess its spelling', () {
      expect(() => canonicalJsonBytes({'x': 0.5}),
          throwsA(isA<CanonicalJsonError>()));
    });

    test('refuses an unpaired surrogate', () {
      expect(() => canonicalJsonBytes({'x': '\uD83D'}),
          throwsA(isA<CanonicalJsonError>()));
    });
  });

  group('one record', () {
    test('reproduces its bytes', () {
      final result = verifyByteWitness(_first(), _firstBytes);
      expect(result.verdict, ByteWitnessVerdict.match);
      expect(result.detail, contains('11 bytes'));
    });

    test('checks a span against the range it cited', () {
      expect(verifyByteWitness(_second(), _secondBytes).verdict,
          ByteWitnessVerdict.match);
    });

    test('is unverifiable, never a match, when nobody supplied the bytes', () {
      final result = verifyByteWitness(_first());
      expect(result.verdict, ByteWitnessVerdict.unverifiable);
      expect(result.failureClass, kWitnessBytesUnavailable);
    });

    test('is tampered when the bytes do not hash to the digest', () {
      final flipped = List<int>.from(_firstBytes)..[0] ^= 1;
      final result = verifyByteWitness(_first(), flipped);
      expect(result.verdict, ByteWitnessVerdict.tampered);
      expect(result.failureClass, kWitnessDigestMismatch);
    });

    test('is tampered on a length that does not match', () {
      final result = verifyByteWitness(_first(), utf8.encode('hello'));
      expect(result.failureClass, kWitnessLengthMismatch);
    });

    test('is tampered on a span the record itself cannot hold', () {
      final record = _second();
      (record['spans'] as List)[0] = {
        'end': 99,
        'note': '',
        'sha256': _spanSha,
        'start': 4,
      };
      // No bytes were supplied. The record refutes itself.
      final result = verifyByteWitness(record);
      expect(result.verdict, ByteWitnessVerdict.tampered);
      expect(result.failureClass, kWitnessSpanOutOfRange);
    });

    test('is unverifiable on a record of another schema', () {
      final record = _first()..['schema'] = 'something.else/v1';
      final result = verifyByteWitness(record);
      expect(result.verdict, ByteWitnessVerdict.unverifiable);
      expect(result.failureClass, kWitnessMalformed);
    });

    test('never throws on hostile input', () {
      for (final bad in <Object?>[null, 7, 'text', <dynamic>[], <String, dynamic>{}]) {
        expect(verifyByteWitness(bad).verdict, ByteWitnessVerdict.unverifiable);
      }
    });
  });

  group('a chain', () {
    test('links, and says plainly that no bytes were checked', () {
      final result = verifyByteWitnessChain([_first(), _second()]);
      expect(result.verdict, ByteWitnessVerdict.unverifiable);
      expect(result.failureClass, kWitnessBytesUnavailable);
      expect(result.head, _secondLink);
      expect(result.checked, 2);
    });

    test('matches when every record resolves to its bytes', () {
      final result =
          verifyByteWitnessChain([_first(), _second()], resolve: _store());
      expect(result.verdict, ByteWitnessVerdict.match);
      expect(result.head, _secondLink);
    });

    test('is tampered when a link does not hold', () {
      final second = _second()..['prev'] = _oddLink;
      final result = verifyByteWitnessChain([_first(), second]);
      expect(result.verdict, ByteWitnessVerdict.tampered);
      expect(result.failureClass, kWitnessLinkBroken);
      expect(result.brokenAt, 1);
    });

    test('refuses a segment lifted out of a longer chain', () {
      final result = verifyByteWitnessChain([_second()]);
      expect(result.verdict, ByteWitnessVerdict.tampered);
      expect(result.failureClass, kWitnessLinkBroken);
      expect(result.brokenAt, 0);
    });

    test('accepts that segment from a caller who holds the earlier head', () {
      final result = verifyByteWitnessChain([_second()],
          start: _firstLink, resolve: _store());
      expect(result.verdict, ByteWitnessVerdict.match);
      expect(result.head, _secondLink);
    });

    test('is unverifiable, not tampered, when a resolver cannot answer', () {
      final result = verifyByteWitnessChain([_first(), _second()],
          resolve: (digest) => throw StateError('the archive is offline'));
      expect(result.verdict, ByteWitnessVerdict.unverifiable);
      expect(result.failureClass, kWitnessBytesUnavailable);
      expect(result.detail, contains('2 could not be resolved'));
    });

    test('reports a partly reachable archive as unverifiable', () {
      final only = {_first()['sha256'] as String: _firstBytes};
      final result = verifyByteWitnessChain([_first(), _second()],
          resolve: (digest) => only[digest]);
      expect(result.verdict, ByteWitnessVerdict.unverifiable);
      expect(result.detail, contains('1 could not be resolved'));
    });

    test('is tampered at the record whose bytes do not reproduce', () {
      final flipped = List<int>.from(_secondBytes)..[0] ^= 1;
      final result = verifyByteWitnessChain([_first(), _second()],
          resolve: (digest) =>
              digest == _first()['sha256'] ? _firstBytes : flipped);
      expect(result.verdict, ByteWitnessVerdict.tampered);
      expect(result.brokenAt, 1);
    });

    test('says a record that does not canonicalize has no link', () {
      // Python would spell a float here and Dart would not agree on how, so
      // this side refuses the record instead of publishing a link that may
      // silently disagree. Unverifiable, never a verdict about the bytes.
      final record = _first()..['context'] = {'ratio': 0.5};
      final result = verifyByteWitnessChain([record]);
      expect(result.verdict, ByteWitnessVerdict.unverifiable);
      expect(result.failureClass, kWitnessMalformed);
      expect(result.head, isNull);
    });

    test('has nothing to check in an empty chain', () {
      expect(verifyByteWitnessChain(<dynamic>[]).verdict,
          ByteWitnessVerdict.unverifiable);
      expect(verifyByteWitnessChain(null).failureClass, kWitnessMalformed);
    });

    test('refuses a start that is not a link', () {
      final result = verifyByteWitnessChain([_first()], start: 'nope');
      expect(result.failureClass, kWitnessMalformed);
    });

    test('always carries what it does not prove', () {
      final result = verifyByteWitnessChain([_first(), _second()]);
      expect(result.doesNotProve, isNotEmpty);
      expect(result.doesNotProve.join(' '), contains('nothing is signed here'));
      expect(result.doesNotProve.last, contains('bind the head'));
    });
  });
}
