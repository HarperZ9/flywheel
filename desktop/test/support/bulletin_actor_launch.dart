import 'dart:convert';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'bulletin_actor_exchange.dart';
import 'bulletin_actor_transport.dart';

/// Trusted launcher inputs are kept separate from the exact actor proposal.
class ActorLaunch {
  ActorLaunch(this.config, this.configSha, Map<String, String> env)
      : runId = env['BULLETIN_ACTOR_RUN_ID'] ?? '',
        slotId = env['BULLETIN_ACTOR_SLOT_ID'] ?? '',
        room = env['BULLETIN_ACTOR_ROOM'] ?? '',
        requestId = env['BULLETIN_ACTOR_REQUEST_ID'] ?? '' {
    try {
      final parents = jsonDecode(env['BULLETIN_ACTOR_PARENT_IDS'] ?? 'null');
      if (parents is! List ||
          parents.isEmpty ||
          parents.length > 2 ||
          !parents.every(actorId) ||
          parents.toSet().length != parents.length ||
          ![runId, slotId, room, requestId].every(actorId) ||
          !actorHash(configSha) ||
          config['mode'] != 'actual_worker_loopback' ||
          config['token'] is! String ||
          (config['token'] as String).isEmpty ||
          !RegExp(r'^jrn_[0-9a-f]{32}$')
              .hasMatch(config['journey_ref'] as String) ||
          !RegExp(r'^cred_[0-9a-f]{32}$')
              .hasMatch(config['credential_ref'] as String) ||
          !actorHash(config['event_head'])) {
        actorInvalid();
      }
      parentIds = List<String>.from(parents);
      gatewayOrigin = actorOrigin(config['base_url'] as String);
      boardOrigin = actorOrigin(config['bulletin_base_url'] as String);
    } on Object {
      actorInvalid();
    }
  }
  final Map<String, Object?> config;
  final String configSha, runId, slotId, room, requestId;
  late final List<String> parentIds;
  late final Uri gatewayOrigin, boardOrigin;
  Map<String, Object?>? _descriptor;
  Map<String, Object?> get descriptor => _descriptor ?? actorInvalid();
  GatewayJourneyBinding get binding => GatewayJourneyBinding(
      config['journey_ref'] as String, config['event_head'] as String);

  void admitDescriptor(Map<String, Object?> value) {
    if (_descriptor != null) actorInvalid();
    actorFields(value, {
      'schema_version',
      'run_id',
      'slot_id',
      'manifest_sha256',
      'gateway_origin',
      'bulletin_origin',
      'fixture_config_sha256',
      'proposal_sha256',
      'request_timeout_ms',
      'remaining_active_ms',
      'review_wait_max_ms'
    });
    if (value['run_id'] != runId ||
        value['slot_id'] != slotId ||
        value['fixture_config_sha256'] != configSha ||
        !actorHash(value['manifest_sha256']) ||
        !actorHash(value['proposal_sha256']) ||
        value['gateway_origin'] != gatewayOrigin.toString() ||
        value['bulletin_origin'] != boardOrigin.toString()) {
      actorInvalid();
    }
    for (final field in {
      'request_timeout_ms': 15000,
      'remaining_active_ms': 240000,
      'review_wait_max_ms': 120000
    }.entries) {
      final v = value[field.key];
      if (v is! int || v < 1 || v > field.value) actorInvalid();
    }
    _descriptor = Map.unmodifiable(value);
  }

  GatewayOperation operation(ActorRecord record) {
    final value = record.value;
    actorFields(value, {
      'schema_version',
      'run_id',
      'slot_id',
      'model_invocation_id',
      'assistant_text_sha256',
      'body_utf8_sha256',
      'proposal'
    });
    if (record.sha256 != descriptor['proposal_sha256'] ||
        value['run_id'] != runId ||
        value['slot_id'] != slotId ||
        !actorId(value['model_invocation_id']) ||
        !actorHash(value['assistant_text_sha256']) ||
        !actorHash(value['body_utf8_sha256'])) {
      actorInvalid();
    }
    final proposal = value['proposal'];
    const fields = {'action', 'room', 'parent_id', 'body'};
    if (proposal is! Map<String, Object?> ||
        proposal.length != fields.length ||
        !proposal.keys.every(fields.contains) ||
        !proposal.values.every((v) => v is String) ||
        proposal['action'] != 'write_reply' ||
        proposal['room'] != room ||
        !parentIds.contains(proposal['parent_id'])) {
      actorInvalid();
    }
    final body = proposal['body'] as String;
    if (utf8.encode(body).length > 4000 ||
        actorDigest(utf8.encode(body)) != value['body_utf8_sha256']) {
      actorInvalid();
    }
    return GatewayOperation.exact(
        action: 'lane.call',
        clientRequestId: requestId,
        credentialRefs: [
          config['credential_ref'] as String
        ],
        operation: {
          'name': 'bulletin',
          'tool': 'board_write_post',
          'governance_tier': 'T2',
          'timeout': 20,
          'args': {
            'room': room,
            'body': body,
            'parent_id': proposal['parent_id']
          },
        });
  }
}
