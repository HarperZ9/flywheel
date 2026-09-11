import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/agent_trace_reader.dart';
import 'package:flywheel_desktop/controllers/agent_trace_controller.dart';
import 'package:flywheel_desktop/models/agent_trace.dart';
import 'package:flywheel_desktop/models/agent_trace_record.dart';
import 'agent_trace_models_test.dart' show fixture, operation, journey;

TraceProjection projection() =>
    TraceProjection.fromJson(fixture('detail_projection'),
        operationRef: operation, journeyRef: journey);

void main() {
  test('private reader uses injected authenticated transport, only exact GET',
      () async {
    final requests = <http.Request>[];
    final client = GatewayClient(
        httpClient: AuthedClient(MockClient((request) async {
      requests.add(request);
      expect(request.method, 'GET');
      expect(request.url.path, '/api/operations/$operation/trace');
      expect(request.url.queryParameters,
          {'ref': projection().traceRef, 'sequence': '0'});
      expect(request.followRedirects, isFalse);
      expect(
          request.headers['Authorization'], 'Bearer synthetic-trace-fixture');
      return http.Response(jsonEncode(fixture('detail')), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }), readToken: () => 'synthetic-trace-fixture'));
    final result = await GatewayAgentTrace(client).read(projection(), 0);
    expect(result.record.payload['duration_s'], 1.25);
    expect(requests, hasLength(1));
  });

  test('fixed error states never expose response bodies or follow redirects',
      () async {
    for (final status in [401, 404, 422, 500, 302]) {
      final client = GatewayClient(
          httpClient: MockClient((_) async => http.Response(
              'private source and credential-like content', status)));
      try {
        await GatewayAgentTrace(client).read(projection(), 0);
        fail('response should fail');
      } on TraceReadException catch (error) {
        expect(error.toString(), isNot(contains('private source')));
        expect(
            error.failure,
            status == 401
                ? TraceReadFailure.unauthorized
                : status == 404
                    ? TraceReadFailure.unavailable
                    : status == 302
                        ? TraceReadFailure.transport
                        : TraceReadFailure.integrity);
      }
    }
  });

  test(
      'closing a private read triggers transport abort without another request',
      () async {
    final cancelled = Completer<void>();
    final started = Completer<void>();
    final aborted = Completer<void>();
    var requests = 0;
    final client =
        GatewayClient(httpClient: MockClient.streaming((request, _) async {
      requests++;
      final abortable = request as http.AbortableRequest;
      abortable.abortTrigger!.then((_) => aborted.complete());
      started.complete();
      return Completer<http.StreamedResponse>().future;
    }));
    final work = GatewayAgentTrace(client)
        .read(projection(), 0, cancelled: cancelled.future);
    final assertion = expectLater(
        work,
        throwsA(isA<TraceReadException>()
            .having((e) => e.failure, 'failure', TraceReadFailure.cancelled)));
    await started.future;
    cancelled.complete();
    await assertion;
    await aborted.future;
    expect(requests, 1);
    client.close();
  });

  test('stream byte budget and total read timeout are enforced', () async {
    final oversized = GatewayClient(
        httpClient: MockClient.streaming((_, __) async =>
            http.StreamedResponse(Stream.value(List.filled(33, 32)), 200)));
    await expectLater(
        GatewayAgentTrace(oversized, maxResponseBytes: 32)
            .read(projection(), 0),
        throwsA(isA<TraceReadException>()
            .having((e) => e.failure, 'failure', TraceReadFailure.limit)));
    // A never-completing send also consumes the same absolute deadline.
    final pending = GatewayClient(
        httpClient: MockClient.streaming(
            (_, __) => Completer<http.StreamedResponse>().future));
    await expectLater(
        GatewayAgentTrace(pending, timeout: const Duration(milliseconds: 5))
            .read(projection(), 0),
        throwsA(isA<TraceReadException>()
            .having((e) => e.failure, 'failure', TraceReadFailure.transport)));
  });

  test('retry repeats only failed read and verifies advertised final head',
      () async {
    var calls = 0;
    final reader = FakeTraceReader((p, seq) async {
      expect(seq, 0);
      if (++calls == 1) {
        throw const TraceReadException(TraceReadFailure.transport);
      }
      return TracePage.fromJson(fixture('detail'),
          operationRef: operation,
          journeyRef: journey,
          traceRef: p.traceRef,
          sequence: seq);
    });
    final state = AgentTraceController(reader, projection());
    await state.loadNext();
    expect(state.failure, TraceReadFailure.transport);
    expect(state.records, isEmpty);
    await state.loadNext();
    expect(state.complete, isTrue);
    expect(state.records.single.canonicalText, contains('naïve ✓'));
    await state.loadNext();
    expect(calls, 2);
    state.dispose();
  });

  test('wrong advertised head is never accepted; disposed reads cannot publish',
      () async {
    final value = fixture('detail')..['trace_head_sha256'] = 'e' * 64;
    final bad = FakeTraceReader((p, seq) async => TracePage.fromJson(value,
        operationRef: operation,
        journeyRef: journey,
        traceRef: p.traceRef,
        sequence: seq));
    final state = AgentTraceController(bad, projection());
    await state.loadNext();
    expect(state.failure, TraceReadFailure.integrity);
    expect(state.records, isEmpty);
    state.dispose();
    final pending = Completer<TracePage>();
    final late = AgentTraceController(
        FakeTraceReader((_, __) => pending.future), projection());
    final work = late.loadNext();
    late.dispose();
    pending.complete(TracePage.fromJson(fixture('detail'),
        operationRef: operation,
        journeyRef: journey,
        traceRef: projection().traceRef,
        sequence: 0));
    await work;
    expect(late.records, isEmpty);
  });
}

class FakeTraceReader implements AgentTraceReader {
  final Future<TracePage> Function(TraceProjection, int) callback;
  FakeTraceReader(this.callback);
  @override
  Future<TracePage> read(TraceProjection projection, int sequence,
          {Future<void>? cancelled}) =>
      callback(projection, sequence);
}
