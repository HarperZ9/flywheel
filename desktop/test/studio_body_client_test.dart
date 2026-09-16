import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/studio_body_client.dart';
import 'package:flywheel_desktop/models/studio_body_models.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('client preserves non-200 body-step receipts', () async {
    Map<String, dynamic>? seenBody;
    final gateway = GatewayClient(
      httpClient: MockClient((request) async {
        seenBody = jsonDecode(request.body) as Map<String, dynamic>;
        expect(request.url.path, '/api/studio/body/step');
        expect(request.followRedirects, isFalse);
        return http.Response(
            jsonEncode({
              'schema': 'flywheel.studio.body.step-response/v1',
              'accepted': false,
              'status': 'deny',
              'action_kind': studioBodySoundActionKind,
              'target': 'flywheel://studio/sound/studio-screen-1/screen',
              'receipt': null,
              'authority_receipt': {
                'decision': 'deny',
                'acted': false,
                'verified': false,
              },
              'errors': ['outside grant'],
            }),
            403,
            headers: {'content-type': 'application/json'});
      }),
    );

    final result = await GatewayStudioBodyClient(gateway).submitStep(
      StudioBodyStepDraft.sound(
        clientActionId: 'client-1',
        idempotencyKey: 'idem-1',
        modelRouteRef: 'openai_responses:vision',
        observationRef: 'obs-screen-frame-1',
        sessionRef: 'studio-screen-1',
        instrumentRef: 'screen',
        seed: 58,
        durationSeconds: 6,
        rootHz: 220,
        captureSessionRef: 'cap-1',
        latestFrameRef: 'display:primary:1',
        latestDeliveredFrameAgeMs: 25,
        modelDelivery: {
          'parts': [
            {
              'kind': 'screen_frame',
              'frame': {
                'session_id': 'cap-1',
                'source_id': 'display:primary',
                'source_sequence': 1,
                'aggregate_sequence': 1,
                'frame_sha256': 'a' * 64,
              },
              'model_route': 'openai_responses:vision',
              'model': 'gpt-5.6-sol',
            }
          ]
        },
      ),
    );

    expect(seenBody?['schema'], studioBodyContractVersion);
    expect(seenBody?['model_route_ref'], 'openai_responses:vision');
    expect(seenBody?['capture_session_ref'], 'cap-1');
    expect(seenBody?['latest_frame_ref'], 'display:primary:1');
    expect(seenBody?['model_delivery'], isA<Map<String, dynamic>>());
    expect(seenBody?['action']['target'],
        'flywheel://studio/sound/studio-screen-1/screen');
    expect(result.accepted, isFalse);
    expect(result.status, 'deny');
    expect(result.authorityDecision, 'deny');
    gateway.close();
  });

  test('client requests snapshots with live-screen capture refs', () async {
    Map<String, dynamic>? seenBody;
    final gateway = GatewayClient(
      httpClient: MockClient((request) async {
        expect(request.url.path, '/api/studio/body/snapshot');
        expect(request.followRedirects, isFalse);
        seenBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
            jsonEncode({
              'schema': 'flywheel.studio.body.snapshot/v1',
              'snapshot': {
                'snapshot_id': 'snap-1',
                'captured_at': '2026-09-15T12:00:00Z',
                'session_ref': 'studio-screen-1',
                'instrument_ref': 'screen',
                'target': 'flywheel://studio/sound/studio-screen-1/screen',
                'capture': {
                  'available': false,
                  'status': 'capture_manager_unavailable'
                },
                'requested_capture': {'validated': false},
                'observations': [
                  {
                    'observation_ref': 'obs-sound',
                    'source': 'flywheel.sound_studio.compose_state/v1',
                    'delivery_mode': 'measured_text_json',
                    'state_sha256': 'b' * 64,
                  }
                ],
              },
            }),
            200,
            headers: {'content-type': 'application/json'});
      }),
    );

    final snapshot = await GatewayStudioBodyClient(gateway).snapshot(
      const StudioBodySnapshotRequest(
        sessionRef: 'studio-screen-1',
        instrumentRef: 'screen',
        captureSessionRef: 'cap-1',
        sourceRef: 'display:primary',
        latestFrameRef: 'display:primary:7',
        frameSha256:
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      ),
    );

    expect(seenBody, {
      'session_ref': 'studio-screen-1',
      'instrument_ref': 'screen',
      'capture_session_ref': 'cap-1',
      'source_ref': 'display:primary',
      'latest_frame_ref': 'display:primary:7',
      'frame_sha256':
          'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    });
    expect(snapshot.primaryObservation?.observationRef, 'obs-sound');
    gateway.close();
  });
}
