// forum_models_test.dart - the forum lane's four reads, including the states
// a running system actually produces.
//
// The gateway proxies these over MCP and returns {"error": ...} when the lane
// is down, so "offline" is a value to render, not an exception. The shapes
// here are the ones the live lane returned.

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/forum_models.dart';

void main() {
  group('offline is a first-class state', () {
    const down = {'error': 'forum lane unavailable: spawn failed'};

    test('status reports the lane\'s own reason, not a synthesized one', () {
      final s = ForumStatus.fromJson(down);
      expect(s.offline, isNotNull);
      expect(s.offline!.reason, contains('spawn failed'));
    });

    test('every read degrades the same way', () {
      expect(ForumLedger.fromJson(down).offline, isNotNull);
      expect(ForumGates.fromJson(down).offline, isNotNull);
      expect(ForumRunRoom.fromJson(down).offline, isNotNull);
    });

    test('an empty error string is not an offline lane', () {
      expect(ForumStatus.fromJson(const {'error': ''}).offline, isNull);
    });
  });

  test('status parses the live envelope', () {
    final s = ForumStatus.fromJson(const {
      'tool': 'forum',
      'tool_version': '1.13.0',
      'status': 'MATCH',
      'native': {
        'role': 'orchestration-routing',
        'current_status': 'campaign orchestration, approval gates',
      },
    });
    expect(s.version, '1.13.0');
    expect(s.status, 'MATCH');
    expect(s.role, 'orchestration-routing');
    expect(s.currentStatus, contains('approval gates'));
  });

  test('an empty ledger is empty, not broken', () {
    final l = ForumLedger.fromJson(const {
      'entries': 0,
      'requests': 0,
      'payload_bytes': 0,
      'checkpoint':
          '0000000000000000000000000000000000000000000000000000000000000000',
      'verified': true,
    });
    expect(l.isEmpty, isTrue);
    expect(l.verified, isTrue,
        reason: 'an empty chain still verifies; that is not acceptance');
    expect(l.offline, isNull);
  });

  test('ledger counters survive a lane that omits fields', () {
    final l = ForumLedger.fromJson(const {'entries': 4});
    expect(l.entries, 4);
    expect(l.answers, 0, reason: 'a missing counter degrades to zero');
    expect(l.verified, isFalse, reason: 'absent is not verified');
  });

  test('no pending gates parses as an empty list', () {
    final g = ForumGates.fromJson(const {'pending': []});
    expect(g.offline, isNull);
    expect(g.pending, isEmpty);
  });

  test('a pending gate carries its run and wave', () {
    final g = ForumGates.fromJson(const {
      'pending': [
        {'run_seq': 12, 'wave': 3, 'reason': 'writes outside the workspace'}
      ]
    });
    expect(g.pending.single.runSeq, 12);
    expect(g.pending.single.wave, 3);
    expect(g.pending.single.label, contains('writes outside'));
  });

  test('a malformed pending entry is skipped, not fatal', () {
    final g = ForumGates.fromJson(const {
      'pending': ['not a map', 7]
    });
    expect(g.pending, isEmpty);
  });

  test('the idle run room is rendered from the lane\'s own brief', () {
    final r = ForumRunRoom.fromJson(const {
      'verified': true,
      'signals': {'pending_gates': 0, 'verifications_ran': 0},
      'brief': {
        'state': 'idle',
        'title': 'No active run',
        'summary': 'No run has been submitted in this room yet.',
        'risk': 'No blocking signals detected.',
        'next_step': 'Submit a request.',
        'bullets': ['Route: not witnessed', 'Answer: missing'],
      },
    });
    expect(r.idle, isTrue);
    expect(r.title, 'No active run');
    expect(r.nextStep, 'Submit a request.');
    expect(r.bullets, hasLength(2));
    expect(r.verificationsRan, 0);
  });

  test('run room signals surface the blocking counts', () {
    final r = ForumRunRoom.fromJson(const {
      'signals': {
        'pending_gates': 2,
        'failed_results': 1,
        'verifications_ran': 5,
      },
      'brief': {'state': 'running'},
    });
    expect(r.pendingGates, 2);
    expect(r.failedResults, 1);
    expect(r.verificationsRan, 5);
    expect(r.idle, isFalse);
  });

  test('a run room with no brief does not crash', () {
    final r = ForumRunRoom.fromJson(const {'verified': false});
    expect(r.title, '');
    expect(r.bullets, isEmpty);
    expect(r.offline, isNull);
  });
}
