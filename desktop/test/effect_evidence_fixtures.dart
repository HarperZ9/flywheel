import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flywheel_desktop/models/agent_trace.dart';
import 'package:flywheel_desktop/models/canonical_json.dart';

import 'agent_trace_models_test.dart' show operation, journey, trace;

Map<String, dynamic> effectDetail() {
  final edited = {'example.txt': 'a' * 64};
  final entryHash =
      _sessionEntryHash(0, 'tool_result', 'private result', '0' * 64);
  final record = <String, dynamic>{
    'schema': 'flywheel.gateway-agent-record/v1',
    'owner_ref': 'owner_${'a' * 32}',
    'journey_ref': journey,
    'operation_ref': operation,
    'trace_ref': trace,
    'sequence': 0,
    'kind': 'ledger',
    'prior_sha256': '0' * 64,
    'payload': {
      'seq': 0,
      'kind': 'tool_result',
      'content': 'private result',
      'meta': {'edited': edited, 'ok': true, 'tool': 'write_file'},
      'prev_hash': '0' * 64,
      'entry_hash': entryHash,
    }
  };
  return _detail(record);
}

TraceProjection witnessProjection(TraceProjection Function(Map<String, dynamic>) parse,
    {String actionDetail = 'action detail'}) {
  final detail = witnessDetail(actionDetail: actionDetail);
  final record = detail['record'] as Map<String, dynamic>;
  final payload = record['payload'] as Map<String, dynamic>;
  final action = payload['action_witness'] as Map<String, dynamic>;
  final receipts = payload['tool_call_receipts'] as Map<String, dynamic>;
  final material = <String, dynamic>{
    'schema': 'flywheel.gateway-agent-projection/v1',
    'operation_ref': operation,
    'journey_ref': journey,
    'state': 'completed',
    'trace_ref': trace,
    'record_count': 1,
    'trace_head_sha256': record['record_sha256'],
    'omissions': ['PRIVATE_CONTENT', 'CREDENTIAL_VALUES', 'UPSTREAM_OUTPUT_LIMITS'],
    'does_not_prove': [
      'NOT_SEMANTIC_TRUTH',
      'NOT_UNLIMITED_TOOL_OUTPUT',
      'ACCEPTED_PREFIX_ONLY_UNTIL_COMPLETED'
    ],
    'effect_evidence': _effectBlock(
        head: record['record_sha256'] as String,
        action: action,
        receipts: receipts),
  };
  return parse({...material, 'projection_sha256': canonicalJsonSha256(material)});
}

Map<String, dynamic> witnessDetail({String actionDetail = 'action detail'}) {
  final action = {
    'schema': 'flywheel.byte-witness-chain/v1',
    'count': 2,
    'head_sha256': 'b' * 64,
    'records': [
      {'private': actionDetail}
    ],
    'does_not_prove': ['semantic correctness'],
  };
  final receipts = {
    'schema': 'flywheel.tool-call-receipt/v1',
    'dir': 'private-receipts',
    'count': 3,
    'chain_head_sha256': 'c' * 64,
  };
  return _detail(<String, dynamic>{
    'schema': 'flywheel.gateway-agent-record/v1',
    'owner_ref': 'owner_${'a' * 32}',
    'journey_ref': journey,
    'operation_ref': operation,
    'trace_ref': trace,
    'sequence': 0,
    'kind': 'result',
    'prior_sha256': '0' * 64,
    'payload': {'action_witness': action, 'tool_call_receipts': receipts}
  });
}

Map<String, dynamic> _detail(Map<String, dynamic> record) {
  final bytes = canonicalJsonBytes(record);
  final digest = canonicalJsonSha256(record);
  return {
    'schema': 'flywheel.gateway-agent-trace-detail/v1',
    'trace_ref': trace,
    'operation_ref': operation,
    'journey_ref': journey,
    'record_count': 1,
    'trace_head_sha256': digest,
    'record': {...record, 'record_sha256': digest},
    'record_canonical_base64': base64Encode(bytes),
    'next_sequence': null,
    'does_not_prove': ['NOT_SEMANTIC_TRUTH', 'NOT_UNLIMITED_TOOL_OUTPUT'],
  };
}

Map<String, dynamic> _effectBlock(
        {required String head,
        required Map<String, dynamic> action,
        required Map<String, dynamic> receipts}) =>
    {
      'schema': 'flywheel.gateway-effect-evidence/v1',
      'scope': 'owner_private_trace_prefix',
      'basis': {
        'trace_ref': trace,
        'record_count': 1,
        'trace_head_sha256': head,
        'terminal_state': 'completed',
        'terminal_basis_event_type': 'operation_started',
        'terminal_basis_event_sha256': 'e' * 64,
      },
      'known_observation_count': 0,
      'known_observations_omitted': 0,
      'known_observations_digest': canonicalJsonSha256([]),
      'known_observations': [],
      'action_witness': _summary(
          kind: 'reported_action_witness_summary',
          pointer: '/payload/action_witness',
          count: 2,
          headField: 'head_sha256',
          head: 'b' * 64,
          value: action,
          recordSha256: head),
      'tool_call_receipts': _summary(
          kind: 'reported_tool_call_receipts_summary',
          pointer: '/payload/tool_call_receipts',
          count: 3,
          headField: 'chain_head_sha256',
          head: 'c' * 64,
          value: receipts,
          recordSha256: head),
      'unknown_effect_scope': [
        'NOT_ROLLBACK',
        'NOT_EFFECT_ABSENCE',
        'NOT_CURRENT_FILESYSTEM_STATE',
        'UNRECORDED_ACTIONS_NOT_EXCLUDED',
        'TOOLS_WITHOUT_POST_EFFECT_FINGERPRINTS_REMAIN_UNKNOWN',
        'EFFECTS_AFTER_TRACE_HEAD_REMAIN_UNKNOWN'
      ],
      'does_not_prove': [
        'semantic correctness',
        'complete workstation observation',
        'current filesystem state',
        'absence of effects outside the accepted trace prefix',
        'rollback or remote cancellation'
      ],
    };

Map<String, dynamic> _summary(
        {required String kind,
        required String pointer,
        required int count,
        required String headField,
        required String head,
        required Map<String, dynamic> value,
        required String recordSha256}) =>
    {
      'status': 'present',
      'kind': kind,
      'trace_sequence': 0,
      'record_sha256': recordSha256,
      'record_kind': 'result',
      'payload_kind': 'result',
      'value_sha256': canonicalJsonSha256(value),
      'count': count,
      headField: head,
      'json_pointer': pointer,
    };

String _sessionEntryHash(int seq, String kind, String content, String prev) {
  final metaJson =
      '{"edited": {"example.txt": "${'a' * 64}"}, "ok": true, '
      '"tool": "write_file"}';
  final bytes = <int>[];
  for (final part in ['$seq', kind, content, metaJson, prev]) {
    bytes.add(0x1f);
    bytes.addAll(utf8.encode(part));
  }
  return sha256.convert(bytes).toString();
}
