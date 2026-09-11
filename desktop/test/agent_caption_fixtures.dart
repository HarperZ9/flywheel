import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flywheel_desktop/client/agent_trace_reader.dart';
import 'package:flywheel_desktop/models/agent_trace.dart';
import 'package:flywheel_desktop/models/agent_trace_record.dart';
import 'package:flywheel_desktop/models/canonical_json.dart';

Map<String, dynamic> captionFixture(String name) => jsonDecode(
    File('../tests/fixtures/native_agent_trace/$name.json').readAsStringSync());

Map<String, dynamic> captionLedger(String kind, String content,
        {Map<String, dynamic> meta = const {}}) =>
    {
      'seq': 0,
      'kind': kind,
      'content': content,
      'meta': meta,
      'prev_hash': traceGenesis,
      'entry_hash': 'a' * 64,
    };

List<Map<String, dynamic>> captionPages(List<Map<String, dynamic>> payloads,
    {String kind = 'ledger'}) {
  var prior = traceGenesis;
  final pages = <Map<String, dynamic>>[];
  for (var sequence = 0; sequence < payloads.length; sequence++) {
    final original =
        Map<String, dynamic>.from(captionFixture('detail')['record'])
          ..remove('record_sha256')
          ..['kind'] = kind
          ..['sequence'] = sequence
          ..['prior_sha256'] = prior
          ..['payload'] = payloads[sequence];
    final bytes = utf8.encode(jsonEncode(original));
    prior = sha256.convert(bytes).toString();
    pages.add(captionFixture('detail')
      ..['record'] = {...original, 'record_sha256': prior}
      ..['record_canonical_base64'] = base64Encode(bytes)
      ..['record_count'] = payloads.length
      ..['next_sequence'] =
          sequence + 1 < payloads.length ? sequence + 1 : null);
  }
  for (final page in pages) {
    page['trace_head_sha256'] = prior;
  }
  return pages;
}

TraceProjection captionProjection(List<Map<String, dynamic>> pages,
    {int? count, String state = 'running'}) {
  final raw = captionFixture('detail_projection')..remove('projection_sha256');
  raw['record_count'] = count ?? pages.length;
  raw['trace_head_sha256'] =
      (pages[(count ?? pages.length) - 1]['record'] as Map)['record_sha256'];
  raw['state'] = state;
  return TraceProjection.fromJson(
      {...raw, 'projection_sha256': canonicalJsonSha256(raw)},
      operationRef: raw['operation_ref'], journeyRef: raw['journey_ref']);
}

TracePage captionPage(Map<String, dynamic> raw, int sequence) =>
    TracePage.fromJson(raw,
        operationRef: raw['operation_ref'],
        journeyRef: raw['journey_ref'],
        traceRef: raw['trace_ref'],
        sequence: sequence);

class CaptionReader implements AgentTraceReader {
  final Future<TracePage> Function(TraceProjection, int, Future<void>?)
      callback;
  CaptionReader(this.callback);
  @override
  Future<TracePage> read(TraceProjection projection, int sequence,
          {Future<void>? cancelled}) =>
      callback(projection, sequence, cancelled);
}
