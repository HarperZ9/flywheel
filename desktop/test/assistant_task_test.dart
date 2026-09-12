import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/assistant/assistant_task_controller.dart';
import 'package:flywheel_desktop/client/assistant_task_api.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/assistant_task.dart';

const run = '0123456789abcdef';
const other = 'fedcba9876543210';
Map<String, dynamic> result({bool verified = true}) => {
      'run_id': run,
      'state': 'done',
      'result': {
        'final': 'Source data stays in Relay',
        'steps': 2,
        'verified': verified,
        'chain_ok': true,
        'final_answer': true,
        'checkpoint': 'a' * 64,
      },
    };

void main() {
  test('only actual Relay states are classified; status aliases stay unknown',
      () {
    for (final (wire, expected) in [
      ('running', AssistantTaskState.running),
      ('done', AssistantTaskState.completed),
      ('error', AssistantTaskState.failed),
      ('interrupted', AssistantTaskState.interrupted),
      ('completed', AssistantTaskState.unknown),
      ('approved', AssistantTaskState.unknown),
    ]) {
      expect(AssistantTask.fromStatus({'run_id': run, 'state': wire})!.state,
          expected);
    }
    expect(AssistantTask.fromStatus({'run_id': run, 'status': 'done'})!.state,
        AssistantTaskState.unknown);
  });

  test('finished execution and reported receipt integrity are separate facts',
      () {
    final task = AssistantTask.fromStatus({'run_id': run, 'state': 'done'})!;
    expect(task.assurance, AssistantTaskAssurance.unchecked);
    expect(task.withResult(result()).assurance,
        AssistantTaskAssurance.reportedIntact);
    expect(task.withResult(result(verified: false)).state,
        AssistantTaskState.completed);
    expect(task.withResult(result(verified: false)).assurance,
        AssistantTaskAssurance.held);
  });

  test(
      'missing result cannot inherit assurance; contradictory run stays unknown',
      () {
    final task = AssistantTask.fromStatus({'run_id': run, 'state': 'done'})!;
    for (final raw in [
      {'run_id': run, 'state': 'done', 'result': null},
      {
        'run_id': run,
        'state': 'done',
        'result': {'verified': true}
      },
    ]) {
      expect(task.withResult(raw).state, AssistantTaskState.completed);
      expect(task.withResult(raw).assurance, AssistantTaskAssurance.unchecked);
      expect(task.withResult(raw).readFailed, isTrue);
      expect(task.withResult(raw).checkpoint, isNull);
    }
    expect(task.withResult({...result(), 'run_id': other}).state,
        AssistantTaskState.unknown);
  });

  test('read uses authenticated gateway routes and never submits on recovery',
      () async {
    final paths = <String>[];
    final api = GatewayAssistantTaskApi(
        GatewayClient(httpClient: MockClient((req) async {
      paths.add(req.url.path);
      expect(req.method, 'GET');
      expect(req.url.queryParameters['run_id'], run);
      return http.Response(
          jsonEncode(req.url.path.endsWith('/status')
              ? {'run_id': run, 'state': 'done'}
              : result()),
          200);
    })));
    final task = await api.read(run);
    expect(task.state, AssistantTaskState.completed);
    expect(paths, ['/api/relay/status', '/api/relay/result']);
  });

  test('invalid references cause no network request', () async {
    var calls = 0;
    final api =
        GatewayAssistantTaskApi(GatewayClient(httpClient: MockClient((_) async {
      calls++;
      return http.Response('{}', 200);
    })));
    for (final ref in [
      '../secret',
      'sk-live-secret',
      'a' * 65,
      run.toUpperCase()
    ]) {
      await expectLater(api.read(ref), throwsFormatException);
    }
    expect(calls, 0);
  });

  test('wrong run stays unknown; lost result preserves completed execution',
      () async {
    var calls = 0;
    final api = GatewayAssistantTaskApi(
        GatewayClient(httpClient: MockClient((req) async {
      calls++;
      return http.Response(jsonEncode({'run_id': other, 'state': 'done'}), 200);
    })));
    expect((await api.read(run)).state, AssistantTaskState.unknown);
    expect(calls, 1);
    final lost = GatewayAssistantTaskApi(
        GatewayClient(httpClient: MockClient((req) async {
      if (req.url.path.endsWith('/result')) {
        throw http.ClientException('private diagnostic');
      }
      return http.Response(jsonEncode({'run_id': run, 'state': 'done'}), 200);
    })));
    final completed = await lost.read(run);
    expect(completed.state, AssistantTaskState.completed);
    expect(completed.assurance, AssistantTaskAssurance.unchecked);
    expect(completed.readFailed, isTrue);
  });

  test('malformed list fails visibly instead of appearing as empty history',
      () async {
    for (final doc in [
      {'error': 'private diagnostic'},
      {
        'runs': [
          {'run_id': '../secret'}
        ]
      },
      {
        'runs': [
          {'run_id': run},
          {'run_id': run}
        ]
      },
    ]) {
      final api = GatewayAssistantTaskApi(GatewayClient(
          httpClient:
              MockClient((_) async => http.Response(jsonEncode(doc), 200))));
      await expectLater(api.recent(), throwsFormatException);
    }
  });

  test(
      'new controller recovers gateway tasks without local claims or submissions',
      () async {
    final api = _Api();
    final first = AssistantTaskController(api)..submitted(run);
    expect(first.tasks.single.state, AssistantTaskState.submitted);
    final reopened = AssistantTaskController(api);
    await reopened.recover();
    expect(reopened.tasks.single.runId, other);
    expect(reopened.tasks.single.state, AssistantTaskState.running);
    expect(api.reads, isEmpty);
    first.dispose();
    reopened.dispose();
  });

  test('failed refresh retains run ref and clears reassuring cached state',
      () async {
    final api = _Api();
    final controller = AssistantTaskController(api)..submitted(run);
    await controller.refresh(run);
    expect(controller.tasks.single.state, AssistantTaskState.completed);
    api.fail = true;
    await controller.refresh(run);
    expect(controller.tasks.single.runId, run);
    expect(controller.tasks.single.state, AssistantTaskState.unknown);
    await controller.recover();
    expect(controller.unavailable, isTrue);
    expect(controller.tasks, hasLength(1));
    controller.dispose();
  });

  test('concurrent refreshes of one task perform one read', () async {
    final api = _Api()..pending = Completer<AssistantTask>();
    final controller = AssistantTaskController(api)..submitted(run);
    final first = controller.refresh(run);
    await controller.refresh(run);
    expect(api.reads, [run]);
    api.pending!.complete(const AssistantTask(run, AssistantTaskState.running));
    await first;
    controller.dispose();
  });

  test('a delayed list response cannot overwrite a newer terminal read',
      () async {
    final api = _Api()..recentPending = Completer<List<AssistantTask>>();
    final controller = AssistantTaskController(api)..submitted(run);
    final loading = controller.recover();
    await controller.refresh(run);
    api.recentPending!
        .complete([const AssistantTask(run, AssistantTaskState.running)]);
    await loading;
    expect(controller.tasks.single.state, AssistantTaskState.completed);
    controller.dispose();
  });

  test('contradictory error envelopes do not inherit a successful state', () {
    expect(
        AssistantTask.fromStatus(
                {'run_id': run, 'state': 'done', 'error': 'failed'})!
            .state,
        AssistantTaskState.unknown);
    final task = AssistantTask.fromStatus({'run_id': run, 'state': 'done'})!;
    expect(task.withResult({...result(), 'error': 'failed'}).state,
        AssistantTaskState.unknown);
  });
}

class _Api implements AssistantTaskApi {
  bool fail = false;
  Completer<AssistantTask>? pending;
  Completer<List<AssistantTask>>? recentPending;
  final reads = <String>[];
  @override
  Future<List<AssistantTask>> recent() async {
    if (fail) throw StateError('private diagnostic');
    return recentPending?.future ??
        Future.value([const AssistantTask(other, AssistantTaskState.running)]);
  }

  @override
  Future<AssistantTask> read(String runId) async {
    reads.add(runId);
    if (fail) throw StateError('private diagnostic');
    return pending?.future ??
        Future.value(const AssistantTask(run, AssistantTaskState.completed));
  }
}
