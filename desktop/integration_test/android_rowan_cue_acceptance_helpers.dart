part of 'android_rowan_cue_acceptance_test.dart';

Future<_HarnessMount> _mountHarness(
  WidgetTester tester, {
  required GatewayClient client,
  required JourneySessionStore store,
  required GatewayJourneyBinding binding,
  required GatewayOperationController grants,
}) async {
  final operationKey = GlobalKey();
  final rowan = RowanOperationController(client, sessionStore: store)
    ..setEndpoint('stub')
    ..setMaxStepsOverride(1);
  final host = RowanOperationHostAdapter(rowan);
  final sharing = LiveScreenSharing(client);
  final cues = ShellRowanCues(operationHost: host, screenSharing: sharing);

  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: GatewayOperationScope(
      authorize: (_, operation, current, dispatch) =>
          _authorize(grants, binding, operation, current, dispatch),
      child: _RowanCueAcceptanceSurface(key: operationKey, cues: cues),
    ),
  ));
  await tester.pumpAndSettle();
  return _HarnessMount(
    rowan: rowan,
    host: host,
    sharing: sharing,
    cues: cues,
    operationKey: operationKey,
  );
}

Future<Map<String, Object?>> _openControlsAndOptIn(
  WidgetTester tester,
  ShellRowanCues cues,
) async {
  final initialEnabled = cues.controller.settings.enabled;
  final initialMuted = cues.controller.settings.muted;
  expect(initialEnabled, isFalse);
  expect(initialMuted, isFalse);
  await tester.tap(find.byTooltip('Rowan voice'));
  await tester.pumpAndSettle();
  expect(find.byKey(const Key('rowan-action-cues-enabled')), findsOneWidget);
  expect(find.byKey(const Key('rowan-action-cues-muted')), findsOneWidget);
  await tester.tap(find.byKey(const Key('rowan-action-cues-enabled')));
  await tester.pumpAndSettle();
  expect(cues.controller.settings.enabled, isTrue);
  expect(cues.controller.settings.muted, isFalse);
  return {
    'opened_rowan_voice_controls': true,
    'initial_enabled': initialEnabled,
    'initial_muted': initialMuted,
    'enabled_after_opt_in': cues.controller.settings.enabled,
    'muted_after_opt_in': cues.controller.settings.muted,
  };
}

Future<Map<String, Object?>> _toggleMuteAndExerciseSuppression(
  WidgetTester tester,
  ShellRowanCues cues,
  RowanOperationController rowan,
) async {
  final beforeTelemetry = cues.controller.telemetry.length;
  await tester.tap(find.byKey(const Key('rowan-action-cues-muted')));
  await tester.pumpAndSettle();
  expect(cues.controller.settings.muted, isTrue);
  final event = _eventFromCurrentSnapshot(rowan);
  final decision = await tester.runAsync(() => cues.controller.handle(event));
  final afterTelemetry = cues.controller.telemetry.length;
  expect(decision?.outcome, RowanActionCueOutcome.suppressed);
  expect(decision?.reason, RowanActionCueReason.muted);
  expect(afterTelemetry, beforeTelemetry);
  return {
    'muted_after_toggle': cues.controller.settings.muted,
    'muted_decision_outcome': decision?.outcome.name,
    'muted_decision_reason': decision?.reason.name,
    'telemetry_count_before_muted_event': beforeTelemetry,
    'telemetry_count_after_muted_event': afterTelemetry,
  };
}

Future<Map<String, Object?>> _exerciseDuplicateOrCooldown(
  ShellRowanCues cues,
  RowanOperationController rowan,
) async {
  final event = _eventFromCurrentSnapshot(rowan);
  final first = await cues.controller.handle(event);
  final acceptedFirst = _isDuplicateOrCooldown(first);
  final second = acceptedFirst ? first : await cues.controller.handle(event);
  final accepted = _isDuplicateOrCooldown(second);
  return {
    'ok': accepted,
    'first_decision': _decisionJson(first),
    'second_decision': _decisionJson(second),
    'accepted_reason': second.reason.name,
  };
}

RowanActionCueEvent _eventFromCurrentSnapshot(RowanOperationController rowan) {
  final snapshot = rowan.snapshot;
  if (snapshot == null) throw StateError('operation snapshot missing');
  return RowanActionCueEvent.fromOperationSnapshot(snapshot);
}

bool _isDuplicateOrCooldown(RowanActionCueDecision decision) =>
    decision.outcome == RowanActionCueOutcome.suppressed &&
    (decision.reason == RowanActionCueReason.duplicateEvent ||
        decision.reason == RowanActionCueReason.cooldown);

Future<RowanActionCueTelemetry> _waitForOperationTelemetry(
  ShellRowanCues cues, {
  required int minCount,
}) async {
  for (var i = 0; i < 80; i++) {
    final matches = cues.controller.telemetry
        .where((item) => item.operationRef != null)
        .toList(growable: false);
    if (matches.length >= minCount) return matches.last;
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('Rowan operation cue telemetry was not observed');
}

Future<Map<String, Object?>> _waitForNativePlayerCompletion(
  ShellRowanCues cues,
) async {
  const timeout = Duration(seconds: 12);
  try {
    await cues.controller.player.completions.first.timeout(timeout);
    return {
      'native_player_completion_observed': true,
      'completion_timeout_ms': timeout.inMilliseconds,
    };
  } on TimeoutException {
    return {
      'native_player_completion_observed': false,
      'completion_timeout_ms': timeout.inMilliseconds,
      'reason': 'native_player_completion_timeout',
    };
  }
}

Future<Object?> _authorize(
  GatewayOperationController grants,
  GatewayJourneyBinding binding,
  GatewayOperation operation,
  GatewayOperationSupplier current,
  Future<Object?> Function(Map<String, dynamic>) dispatch,
) async {
  final prepared = await grants.prepare(
    operation,
    binding: binding,
    currentOperation: current,
    currentBinding: () => binding,
  );
  if (!prepared) {
    return GatewayAuthorizationOutcome.failure(
      grants.failure ??
          const GatewayOperationFailure(
            'PREPARE_FAILED',
            'Grant prepare failed',
          ),
    );
  }
  final value = await grants.approveAndDispatch(dispatch);
  return value == null
      ? const GatewayAuthorizationOutcome.denied()
      : GatewayAuthorizationOutcome.value(value);
}

Future<String> _waitForRequestSha(JourneySessionStore store) async {
  for (var i = 0; i < 80; i++) {
    final value = store.load()?.operationRequestSha256;
    if (value != null && value.isNotEmpty) return value;
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('operation request hash was not stored');
}

Future<Map<String, Object?>> _matchingOperations(
  GatewayClient client,
  String journeyRef,
  String requestSha, {
  bool requireCompletedTerminal = false,
}) async {
  for (var i = 0; i < 40; i++) {
    final page =
        await GatewayOperations(client).listByJourney(journeyRef, limit: 50);
    final matches = page.operations
        .where(
          (item) =>
              page.requestSha256ByOperation[item.operationRef] == requestSha,
        )
        .toList(growable: false);
    if (!requireCompletedTerminal && (matches.isNotEmpty || i == 39)) {
      return _operationSetReceipt(page, matches);
    }
    if (requireCompletedTerminal && matches.length == 1) {
      final match = matches.single;
      if (match.state == OperationState.completed) {
        return _operationSetReceipt(page, matches);
      }
      if (match.isTerminal && match.state != OperationState.completed) {
        throw StateError('operation terminal state was not completed');
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('completed terminal operation was not observed');
}

Map<String, Object?> _operationSetReceipt(
  OperationListPage page,
  List<OperationSnapshot> matches,
) {
  final single = matches.length == 1 ? matches.single : null;
  return {
    'operation_count_for_request': matches.length,
    'operation_refs': matches.map((item) => item.operationRef).toList(),
    'operation_set': page.toJson(),
    'snapshot': single?.toJson(),
    'terminal_operation_ref':
        single != null && single.isTerminal ? single.operationRef : null,
    'terminal_state': single?.toJson()['state'],
    'terminal_completed': single?.state == OperationState.completed,
    'terminal_result_sha256': single?.resultSha256,
  };
}
