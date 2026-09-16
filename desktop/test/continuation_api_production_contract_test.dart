import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/continuation_api.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';

void main() {
  test('preview parses production route response for Git SHA-1 repositories',
      () async {
    final workspace =
        await Directory.systemTemp.createTemp('fw-continuation-sha1-');
    final state =
        await Directory.systemTemp.createTemp('fw-continuation-state-');
    addTearDown(() async {
      await workspace.delete(recursive: true);
      await state.delete(recursive: true);
    });
    await _runGit(workspace, ['init', '--object-format=sha1', '-q']);
    await File('${workspace.path}${Platform.pathSeparator}README.md')
        .writeAsString('Continue this work.\n');
    await _runGit(workspace, ['add', 'README.md']);
    await _runGit(workspace, [
      '-c',
      'user.email=a@example.invalid',
      '-c',
      'user.name=A',
      'commit',
      '-q',
      '-m',
      'init',
    ]);
    final routeResponse = await _productionPreview(
      workspace: workspace,
      state: state,
    );
    expect(routeResponse['status'], 200);
    final body = Map<String, dynamic>.from(routeResponse['body'] as Map);
    expect(
      body['repo'],
      containsPair('head', matches(RegExp(r'^[0-9a-f]{40}$'))),
    );

    final api = GatewayContinuationApi(
      GatewayClient(
        baseUrl: 'http://127.0.0.1:8799',
        httpClient: MockClient((request) async {
          expect(request.url.path, '/api/continuation/preview');
          return http.Response(jsonEncode(body), 200);
        }),
      ),
    );

    final preview = await api.preview(root: workspace.path);

    expect(preview.readyToStart, isTrue);
    expect(preview.head, body['repo']['head']);
  });
}

Directory _repoRoot() {
  var current = Directory.current;
  while (true) {
    if (File(
      '${current.path}${Platform.pathSeparator}harness'
      '${Platform.pathSeparator}continuation_route.py',
    ).existsSync()) {
      return current;
    }
    final parent = current.parent;
    if (parent.path == current.path) {
      throw StateError('could not find Flywheel repository root');
    }
    current = parent;
  }
}

Future<void> _runGit(Directory root, List<String> args) async {
  final result = await Process.run('git', args, workingDirectory: root.path);
  if (result.exitCode != 0) {
    throw StateError('git ${args.join(' ')} failed: ${result.stderr}');
  }
}

Future<Map<String, dynamic>> _productionPreview({
  required Directory workspace,
  required Directory state,
}) async {
  final repo = _repoRoot();
  final script = File('${state.path}${Platform.pathSeparator}preview_route.py');
  await script.writeAsString('''
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from harness.continuation_route import handle_continuation_post

workspace = Path(sys.argv[2])
state = Path(sys.argv[3])
result, status = handle_continuation_post(
    "/api/continuation/preview",
    json.dumps({"root": str(workspace)}).encode("utf-8"),
    owner_ref="owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    state_root=state,
    root=None,
    clock=lambda: "2026-09-16T12:00:00Z",
)
print(json.dumps({"status": status, "body": result}))
''');
  final result = await Process.run(
    'python',
    [script.path, repo.path, workspace.path, state.path],
    workingDirectory: repo.path,
  );
  if (result.exitCode != 0) {
    throw StateError('continuation route failed: ${result.stderr}');
  }
  return Map<String, dynamic>.from(
    jsonDecode(result.stdout as String) as Map,
  );
}
