import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'support/bulletin_actor_launch.dart';
import 'support/bulletin_actor_exchange.dart';

void main() {
  const hash =
      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  final config = {
    'base_url': 'http://127.0.0.1:12345',
    'bulletin_base_url': 'http://127.0.0.1:54321',
    'journey_ref': 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'event_head': hash,
    'credential_ref': 'cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'token': 'synthetic-private',
    'mode': 'actual_worker_loopback'
  };
  Map<String, Object?> descriptor(String proposalSha) => {
        'schema_version': 1,
        'run_id': 'run-1',
        'slot_id': 'slot-1',
        'manifest_sha256': hash,
        'gateway_origin': config['base_url'],
        'bulletin_origin': config['bulletin_base_url'],
        'fixture_config_sha256': hash,
        'proposal_sha256': proposalSha,
        'request_timeout_ms': 10000,
        'remaining_active_ms': 100000,
        'review_wait_max_ms': 10000,
      };
  final env = {
    'BULLETIN_ACTOR_RUN_ID': 'run-1',
    'BULLETIN_ACTOR_SLOT_ID': 'slot-1',
    'BULLETIN_ACTOR_ROOM': 'findings',
    'BULLETIN_ACTOR_PARENT_IDS': '["source-1","decoy-1"]',
    'BULLETIN_ACTOR_REQUEST_ID': 'request-1'
  };
  Map<String, Object?> proposal(String body) => {
        'schema_version': 1,
        'run_id': 'run-1',
        'slot_id': 'slot-1',
        'model_invocation_id': 'generation-2',
        'assistant_text_sha256': hash,
        'body_utf8_sha256': actorDigest(utf8.encode(body)),
        'proposal': {
          'action': 'write_reply',
          'room': 'findings',
          'parent_id': 'decoy-1',
          'body': body,
        },
      };
  test(
      'trusted scope permits wrong in-scope semantics without normalizing bytes',
      () {
    final raw = proposal('  {"task_id":"wrong","state":"reported"} 🌱\n');
    final record = ActorRecord(utf8.encode(jsonEncode(raw)));
    final launch = ActorLaunch(config, hash, env);
    launch.admitDescriptor(descriptor(record.sha256));
    final operation = launch.operation(record);
    expect(operation.operation['args'], {
      'room': 'findings',
      'parent_id': 'decoy-1',
      'body': (raw['proposal'] as Map)['body']
    });
  });
  test('descriptor config origin IDs and exact shape are bound', () {
    for (final change in [
      <String, Object?>{'slot_id': 'other'},
      {'gateway_origin': 'http://127.0.0.1:99'},
      {'fixture_config_sha256': 'b' * 64},
      {'schema_version': true},
      {'extra': 'field'},
      {'review_wait_max_ms': 120001}
    ]) {
      final launch = ActorLaunch(config, hash, env);
      expect(() => launch.admitDescriptor({...descriptor(hash), ...change}),
          throwsA(isA<ActorExchangeError>()));
    }
  });
  test(
      'outside parent, wrong body hash, extra action fields and changed bytes denied',
      () {
    for (final kind in ['parent', 'hash', 'extra', 'digest']) {
      final raw = proposal('wrong in-scope content');
      if (kind == 'parent') (raw['proposal'] as Map)['parent_id'] = 'outside';
      if (kind == 'extra') {
        (raw['proposal'] as Map)['credential_ref'] = 'untrusted';
      }
      if (kind == 'hash') raw['body_utf8_sha256'] = 'b' * 64;
      final record = ActorRecord(utf8.encode(jsonEncode(raw)));
      final launch = ActorLaunch(config, hash, env);
      launch
          .admitDescriptor(descriptor(kind == 'digest' ? hash : record.sha256));
      expect(
          () => launch.operation(record), throwsA(isA<ActorExchangeError>()));
    }
  });
}
