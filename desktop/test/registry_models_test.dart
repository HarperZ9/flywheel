// registry_models_test.dart - the engine's registries, including the empty
// states a fresh install actually produces.
//
// These shapes came from the live engine: hooks, skills and packs all return
// {schema, <list>, count} and are empty on a clean run root. Empty is a true
// state, so it must read as empty rather than as a failure.

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/registry_models.dart';

void main() {
  group('named registries', () {
    test('the live empty shape reads as empty, not broken', () {
      final r = NamedRegistry.fromJson(
          const {'schema': 'flywheel.hook-registry/v1', 'hooks': [], 'count': 0},
          'hooks');
      expect(r.isEmpty, isTrue);
      expect(r.error, isNull);
      expect(r.countDisagrees, isFalse);
    });

    test('rows are named from the engine\'s own name field', () {
      final r = NamedRegistry.fromJson(const {
        'skills': [
          {'name': 'summarize'},
          {'name': 'extract'}
        ],
        'count': 2
      }, 'skills');
      expect(r.names, ['summarize', 'extract']);
      expect(r.count, 2);
    });

    test('a count that disagrees with the rows is surfaced, not smoothed', () {
      // The engine says nine; it sent one. That gap is the engine having more
      // to say than this page shows, and inventing agreement would hide it.
      final r = NamedRegistry.fromJson(const {
        'packs': [
          {'name': 'physics'}
        ],
        'count': 9
      }, 'packs');
      expect(r.countDisagrees, isTrue);
      expect(r.count, 9, reason: 'the engine\'s count is reported, not len()');
    });

    test('an error degrades to an unreadable registry', () {
      final r = NamedRegistry.fromJson(const {'error': 'store locked'}, 'hooks');
      expect(r.error, 'store locked');
      expect(r.names, isEmpty);
    });

    test('a wrongly typed list yields no rows rather than throwing', () {
      expect(NamedRegistry.fromJson(const {'hooks': 'none'}, 'hooks').names,
          isEmpty);
    });
  });

  group('loops', () {
    test('a loop closes only when every edge it names executed', () {
      final r = LoopRegister.fromJson(const {
        'loops': [
          {
            'name': 'learning',
            'question': 'does understanding compound?',
            'edges': [
              {'executed': true},
              {'executed': true}
            ]
          },
          {
            'name': 'uplift',
            'edges': [
              {'executed': true},
              {'executed': false}
            ]
          }
        ],
        'closed_count': 1,
        'total': 2
      });
      expect(r.loops.first.closed, isTrue);
      expect(r.loops.last.closed, isFalse,
          reason: 'one edge that never ran keeps the loop open');
      expect(r.closedCount, 1);
    });

    test('a loop with no edges is not closed', () {
      final r = LoopRegister.fromJson(const {
        'loops': [
          {'name': 'empty', 'edges': []}
        ]
      });
      expect(r.loops.single.closed, isFalse,
          reason: 'nothing measured is not the same as nothing failed');
    });

    test('an unmeasured register is empty, not an error', () {
      final r = LoopRegister.fromJson(const {'loops': [], 'total': 0});
      expect(r.loops, isEmpty);
      expect(r.error, isNull);
    });
  });

  group('credential handles', () {
    test('handles are names, and the model has nowhere to put a value', () {
      final h = CredentialHandles.fromJson(const {
        'handles': [
          {'ref': 'anthropic'},
          {'ref': 'openrouter'}
        ]
      });
      expect(h.handles, ['anthropic', 'openrouter']);
    });

    test('no bound handle is an empty list, not an error', () {
      final h = CredentialHandles.fromJson(const {'handles': []});
      expect(h.handles, isEmpty);
      expect(h.error, isNull);
    });
  });

  group('credo', () {
    test('the belief carries the digest that makes it quotable', () {
      const digest =
          '9f2c4a1b8e7d6053f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708';
      final c = Credo.fromJson(const {
        'credo': 'Knowledge is an open surface.',
        'sha256': digest,
      });
      expect(c.text, contains('open surface'));
      expect(c.sha256, hasLength(64));
    });

    test('an unreadable credo says so instead of showing nothing', () {
      final c = Credo.fromJson(const {'error': 'not found'});
      expect(c.error, 'not found');
      expect(c.text, isEmpty);
    });
  });
}
