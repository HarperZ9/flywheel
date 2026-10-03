part of 'android_rowan_cue_acceptance_test.dart';

Future<Map<String, Object?>> _authControls(String baseUrl, String token) async {
  final unauthHttp = http.Client();
  final wrongHttp = http.Client();
  try {
    final missing =
        await GatewayClient(baseUrl: baseUrl, httpClient: unauthHttp).isAlive();
    final wrong = await GatewayClient(
      baseUrl: baseUrl,
      httpClient: AuthedClient(wrongHttp, readToken: () => 'wrong-token'),
    ).isAlive();
    return {
      'missing_token_ok': missing,
      'wrong_token_ok': wrong,
      'token_sha256': _sha(token),
      'token_length': token.length,
    };
  } finally {
    unauthHttp.close();
    wrongHttp.close();
  }
}

Map<String, Object?> _decisionJson(RowanActionCueDecision decision) => {
      'outcome': decision.outcome.name,
      'reason': decision.reason.name,
      'caption': decision.caption,
      'telemetry': decision.telemetry?.toJson(),
    };

Map<String, Object?>? _captionJson(RowanActionCueCaptionState? caption) =>
    caption == null
        ? null
        : {
            'caption': caption.caption,
            'caption_sha256': caption.captionSha256,
            'playback_provenance_sha256': caption.playbackProvenanceSha256,
            'recorded_replay': caption.recordedReplay,
            'source': caption.source.name,
            'operation_ref': caption.operationRef,
            'event_ref': caption.eventRef,
          };

Map<String, Object?> _nativePlaybackFacts(
  ShellRowanCues cues,
  RowanActionCueTelemetry? telemetry,
  Map<String, Object?>? completion,
) =>
    {
      'player_runtime_type': cues.controller.player.runtimeType.toString(),
      'played_telemetry_count': cues.controller.telemetry.length,
      'playback_accepted_by_player_future': telemetry != null,
      'native_player_completion_observed':
          completion?['native_player_completion_observed'] == true,
      'native_player_completion': completion,
      'event_kind': telemetry?.kind.wire,
      'operation_ref': telemetry?.operationRef,
      'event_ref': telemetry?.eventRef,
      'clip_id': telemetry?.clipId,
      'clip_sha256': telemetry?.clipSha256,
      'audio_sha256': telemetry?.audioSha256,
      'caption_sha256': telemetry?.captionSha256,
      'playback_provenance_sha256': telemetry?.playbackProvenanceSha256,
      'audio_plugin_acceptance_boundary':
          'player completion stream observed when true; automated test does not prove audible output',
      'audible_output_confirmed': false,
    };

Map<String, Object?> _receipt(
  String phase,
  ConnectionConfig config,
  String token,
  Map<String, Object?> phaseData,
) =>
    {
      'schema': 'flywheel.android-rowan-cue-acceptance-phase/v1',
      'run_id': _runIdValue(),
      'phase': phase,
      'platform': Platform.operatingSystem,
      'transport': {'mode': 'usb_reverse'},
      'connection': {
        'base_url': config.effectiveBaseUrl,
        'is_remote': config.isRemote,
        'token_sha256': _sha(token),
        'token_length': token.length,
      },
      ...phaseData,
      'limits': const [
        'USB reverse only; does not prove LAN or Tailscale reachability',
        'endpoint stub only; does not prove a live provider or release network',
        'native player completion is recorded separately from audible human confirmation',
      ],
    };

void _emit(Map<String, Object?> receipt, String token) {
  final encoded = jsonEncode(receipt);
  if (encoded.contains(token)) throw StateError('receipt leaked token');
  // ignore: avoid_print
  print('$_prefix$encoded');
}

String _runIdValue() => _runId.isNotEmpty
    ? _runId
    : 'android_rowan_${DateTime.now().microsecondsSinceEpoch}';
String _sha(String value) => sha256.convert(utf8.encode(value)).toString();
