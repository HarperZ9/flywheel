import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/writing_api.dart';

void main() {
  test('GatewayWritingApi uses the private Writing route contract', () async {
    final seen = <String>[];
    final client = GatewayClient(httpClient: MockClient((request) async {
      seen.add('${request.method} ${request.url.path}');
      final body = request.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(request.body) as Map<String, dynamic>;
      if (request.url.path == '/api/writing/status') {
        return http.Response(jsonEncode({'schema': 's', 'projects': []}), 200);
      }
      if (request.url.path == '/api/writing/project') {
        expect(request.url.queryParameters['journey_ref'], 'jrn_a');
        return http.Response(jsonEncode(_project()), 200);
      }
      if (request.url.path == '/api/writing/revision/prepare') {
        expect(body['body'], 'draft');
        return http.Response(jsonEncode(_proposal('rev_1')), 200);
      }
      if (request.url.path == '/api/writing/proposal/approve') {
        expect(body, {'proposal_ref': 'prp_1'});
        return http.Response(jsonEncode({'grant_ref': 'gnt_1'}), 200);
      }
      if (request.url.path == '/api/writing/proposal/commit') {
        expect(body, {'proposal_ref': 'prp_1', 'grant_ref': 'gnt_1'});
        return http.Response(jsonEncode({'event_head_sha256': 'h2'}), 200);
      }
      return http.Response('{}', 404);
    }));
    final api = GatewayWritingApi(client);
    expect((await api.status()).projects, isEmpty);
    expect((await api.project('jrn_a')).sections.single.heading, 'Intro');
    expect((await api.prepareRevision(
      journeyRef: 'jrn_a',
      expectedEventHead: 'h1',
      projectRef: 'wpr_a',
      sectionRef: 'sec_intro',
      body: 'draft',
      clientRequestId: 'r1',
    )).proposalRef, 'prp_1');
    expect((await api.approve('prp_1'))['grant_ref'], 'gnt_1');
    expect((await api.commit('prp_1', 'gnt_1'))['event_head_sha256'], 'h2');
    expect(seen, [
      'GET /api/writing/status',
      'GET /api/writing/project',
      'POST /api/writing/revision/prepare',
      'POST /api/writing/proposal/approve',
      'POST /api/writing/proposal/commit',
    ]);
  });
}

Map<String, dynamic> _proposal(String id) => {
      'proposal_ref': 'prp_1',
      'approval_required': true,
      'artifact_id': id,
      'artifact_kind': 'revision',
    };

Map<String, dynamic> _project() => {
      'schema': 'flywheel.writing-project-view/v1',
      'project_ref': 'wpr_a',
      'journey_ref': 'jrn_a',
      'event_head_sha256': 'h1',
      'source_packet': {
        'source_packet_ref': 'packet',
        'sources': [],
        'does_not_prove': []
      },
      'sections': [
        {'section_ref': 'sec_intro', 'heading': 'Intro', 'current_body': 'Body'}
      ],
      'diagnostics': [],
      'cards': [],
      'candidates': [],
      'decisions': [],
      'reviews': [],
      'exports': [],
      'does_not_prove': []
    };
