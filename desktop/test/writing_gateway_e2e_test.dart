import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/writing_api.dart';

const _projectRef = 'wpr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _sectionRef = 'sec_recommendation';

void main() {
  test('GatewayWritingApi completes a live Writing gateway workflow', () async {
    final gateway = await _LiveWritingGateway.start();
    addTearDown(gateway.close);
    final api = gateway.api;

    expect((await api.status()).projects, isEmpty);
    final init = await api.prepareInit(
      brief: _brief(),
      sourcePacket: _sourcePacket(),
      clientRequestId: 'native-e2e-init',
    );
    await expectLater(
        api.commit(init.proposalRef, 'gnt_00000000000000000000000000000000'),
        throwsA(isA<GatewayException>()
            .having((error) => error.statusCode, 'statusCode', 422)
            .having((error) => error.errorCode, 'errorCode',
                'PERMISSION_REQUIRED')));
    var ack = await api.commit(init.proposalRef,
        (await api.approve(init.proposalRef))['grant_ref'] as String);
    final journeyRef = ack['journey_ref'] as String;
    var head = ack['event_head_sha256'] as String;

    final section = await api.prepareSection(
      journeyRef: journeyRef,
      expectedEventHead: head,
      section: _section(),
      clientRequestId: 'native-e2e-section',
    );
    ack = await _approveCommit(api, section.proposalRef);
    head = ack['event_head_sha256'] as String;

    final revision = await api.prepareRevision(
      journeyRef: journeyRef,
      expectedEventHead: head,
      projectRef: _projectRef,
      sectionRef: _sectionRef,
      body: 'Recommendation: hold.\n',
      clientRequestId: 'native-e2e-draft',
    );
    ack = await _approveCommit(api, revision.proposalRef);
    head = ack['event_head_sha256'] as String;

    final review = await api.prepareReview(
      journeyRef: journeyRef,
      expectedEventHead: head,
      projectRef: _projectRef,
      clientRequestId: 'native-e2e-review',
    );
    expect(review.artifactKind, 'review');
    ack = await _approveCommit(api, review.proposalRef);
    head = ack['event_head_sha256'] as String;

    final status = await api.status();
    expect(status.projects.single.journeyRef, journeyRef);
    expect(status.projects.single.eventHeadSha256, head);
    final project = await api.project(journeyRef);
    expect(project.sections.single.currentBody, 'Recommendation: hold.\n');
    expect(project.reviews.single['review_ref'], review.artifactId);
  });
}

Future<Map<String, dynamic>> _approveCommit(
    WritingApi api, String proposalRef) async {
  final grant = await api.approve(proposalRef);
  return api.commit(proposalRef, grant['grant_ref'] as String);
}

Map<String, dynamic> _brief() => {
      'schema': 'flywheel.writing-project-brief/v1',
      'project_ref': _projectRef,
      'mode': 'nonfiction',
      'form': 'essay',
      'working_title': 'Release evidence',
      'audience': 'operators',
      'reader_job': 'decide whether evidence is sufficient',
      'author_intent': 'make a bounded release recommendation',
      'voice_contract': {'style_ref': 'voice_rules'},
      'source_packet_ref': 'packet_main',
      'writing_profile': 'nonfiction',
      'does_not_prove': ['truth'],
    };

Map<String, dynamic> _sourcePacket() => {
      'schema': 'flywheel.writing-source-packet/v1',
      'project_ref': _projectRef,
      'source_packet_ref': 'packet_main',
      'sources': [
        {
          'source_id': 'src_receipt',
          'title': 'Receipt',
          'origin': 'local',
          'allowed_use': 'cite',
        }
      ],
      'does_not_prove': ['source interpretation'],
    };

Map<String, dynamic> _section() => {
      'schema': 'flywheel.writing-section/v1',
      'project_ref': _projectRef,
      'section_ref': _sectionRef,
      'heading': 'Recommendation',
      'purpose': 'state the release decision',
      'reader_entry_state': 'needs a decision',
      'promises': ['states the decision'],
      'order_index': 1,
    };

final class _LiveWritingGateway {
  _LiveWritingGateway._(this.process, this.home, this.client, this.api,
      this._stdout, this._stderr, this._stdoutSub, this._stderrSub);

  final Process process;
  final Directory home;
  final GatewayClient client;
  final GatewayWritingApi api;
  final StringBuffer _stdout, _stderr;
  final StreamSubscription<String> _stdoutSub, _stderrSub;

  static Future<_LiveWritingGateway> start() async {
    final repo = _repoRoot();
    final home =
        await Directory.systemTemp.createTemp('fw-writing-gateway-e2e-');
    final port = await _freePort();
    final process = await Process.start(
      'python',
      ['harness/gateway.py', '--port', '$port', '--root', repo.path],
      workingDirectory: repo.path,
      environment: {
        'FLYWHEEL_HOME': home.path,
        'PYTHONPATH': '',
      },
      includeParentEnvironment: true,
    );
    final stdout = StringBuffer();
    final stderr = StringBuffer();
    final stdoutSub =
        process.stdout.transform(utf8.decoder).listen(stdout.write);
    final stderrSub =
        process.stderr.transform(utf8.decoder).listen(stderr.write);
    final token = File('${home.path}${Platform.pathSeparator}$tokenFilename');
    final client = GatewayClient(
      baseUrl: 'http://127.0.0.1:$port',
      httpClient: AuthedClient(http.Client(), readToken: () {
        if (!token.existsSync()) return null;
        final value = token.readAsStringSync().trim();
        return value.isEmpty ? null : value;
      }),
    );
    final api = GatewayWritingApi(client);
    final gateway = _LiveWritingGateway._(
        process, home, client, api, stdout, stderr, stdoutSub, stderrSub);
    await gateway._waitUntilReady();
    return gateway;
  }

  Future<void> _waitUntilReady() async {
    Object? lastError;
    for (var i = 0; i < 200; i++) {
      if (await _hasExited()) {
        fail(
            'gateway exited before readiness\nstdout:\n$_stdout\nstderr:\n$_stderr');
      }
      try {
        await api.status();
        return;
      } catch (error) {
        lastError = error;
      }
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    fail(
        'gateway did not become ready: $lastError\nstdout:\n$_stdout\nstderr:\n$_stderr');
  }

  Future<bool> _hasExited() async {
    try {
      await process.exitCode.timeout(const Duration(milliseconds: 1));
      return true;
    } on TimeoutException {
      return false;
    }
  }

  Future<void> close() async {
    client.close();
    if (!await _hasExited()) {
      process.kill();
    }
    try {
      await process.exitCode.timeout(const Duration(seconds: 5));
    } on TimeoutException {
      process.kill(ProcessSignal.sigkill);
    }
    await _stdoutSub.cancel();
    await _stderrSub.cancel();
    if (home.existsSync()) {
      home.deleteSync(recursive: true);
    }
  }
}

Directory _repoRoot() {
  var dir = Directory.current.absolute;
  for (var i = 0; i < 6; i++) {
    if (File('${dir.path}${Platform.pathSeparator}harness'
            '${Platform.pathSeparator}gateway.py')
        .existsSync()) {
      return dir;
    }
    final parent = dir.parent;
    if (parent.path == dir.path) break;
    dir = parent;
  }
  throw StateError(
      'could not locate repository root from ${Directory.current.path}');
}

Future<int> _freePort() async {
  final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
  final port = socket.port;
  await socket.close();
  return port;
}
