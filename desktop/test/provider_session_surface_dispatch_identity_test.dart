import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/provider_session_controller.dart';
import 'package:flywheel_desktop/models/provider_session_models.dart';
import 'package:flywheel_desktop/widgets/provider_session_surface.dart';
import 'package:http/http.dart' as http;

import 'support/provider_session_dispatch_identity_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    final binding = TestWidgetsFlutterBinding.instance;
    binding.platformDispatcher.views.first.physicalSize = const Size(1200, 900);
    binding.platformDispatcher.views.first.devicePixelRatio = 1;
  });

  tearDown(() {
    final binding = TestWidgetsFlutterBinding.instance;
    binding.platformDispatcher.views.first.resetPhysicalSize();
    binding.platformDispatcher.views.first.resetDevicePixelRatio();
  });

  testWidgets('turn dispatch blocks if state changes before approval dispatch',
      (tester) async {
    // Break this catches: approving a turn after provider-session state moves
    // sends the old source_operation_ref.
    final controller = ProviderSessionController()..begin(dispatchOperationA);
    final journey = await dispatchJourney();
    addTearDown(controller.dispose);
    addTearDown(journey.dispose);
    Map<String, dynamic>? captured;
    final client = dispatchIdentityClient((request) async {
      if (request.url.path == providerSessionTurnPath) {
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
            dispatchTerminalSse(providerSessionTurnAction), 200);
      }
      return null;
    });
    addTearDown(client.close);
    var mutated = false;
    final authorize = _authorizer(() {
      if (!mutated) {
        controller.begin(dispatchOperationB);
        mutated = true;
      }
    });

    await tester.pumpWidget(
        dispatchIdentityHost(_surface(controller, client), journey, authorize));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Send turn'));
    await tester.pumpAndSettle();

    expect(captured, isNull);
  });

  testWidgets(
      'resume dispatch blocks if cursor changes before approval dispatch',
      (tester) async {
    final controller = ProviderSessionController()..begin(dispatchOperationA);
    controller.acceptProgress(_oldCursor());
    final journey = await dispatchJourney();
    addTearDown(controller.dispose);
    addTearDown(journey.dispose);
    Map<String, dynamic>? captured;
    final client = dispatchIdentityClient((request) async {
      if (request.url.path == providerSessionResumePath) {
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
            dispatchTerminalSse(providerSessionResumeAction), 200);
      }
      return null;
    });
    addTearDown(client.close);
    var mutated = false;
    final authorize = _authorizer(() {
      if (!mutated) {
        controller.acceptProgress(_newCursor());
        mutated = true;
      }
    });

    await tester.pumpWidget(
        dispatchIdentityHost(_surface(controller, client), journey, authorize));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Resume'));
    await tester.pumpAndSettle();

    expect(captured, isNull);
  });

  testWidgets(
      'reconcile dispatch blocks if cursor changes before approval dispatch',
      (tester) async {
    final controller = ProviderSessionController()..begin(dispatchOperationA);
    controller.acceptProgress(_oldCursor(reconcile: true));
    final journey = await dispatchJourney();
    addTearDown(controller.dispose);
    addTearDown(journey.dispose);
    Map<String, dynamic>? captured;
    final client = dispatchIdentityClient((request) async {
      if (request.url.path == providerSessionReconcilePath) {
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
            dispatchTerminalSse(providerSessionReconcileAction), 200);
      }
      return null;
    });
    addTearDown(client.close);
    var mutated = false;
    final authorize = _authorizer(() {
      if (!mutated) {
        controller.acceptProgress(_newCursor(reconcile: true));
        mutated = true;
      }
    });

    await tester.pumpWidget(
        dispatchIdentityHost(_surface(controller, client), journey, authorize));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Reconcile'));
    await tester.pumpAndSettle();

    expect(captured, isNull);
  });
}

GatewayOperationAuthorizer _authorizer(VoidCallback mutate) =>
    (context, operation, currentOperation, dispatch) async {
      mutate();
      final current = currentOperation();
      if (current == null || current != operation) return null;
      return dispatch(
          operation.finalBody(dispatchJourneyBinding, 'gnt_$dispatchIdA'));
    };

Widget _surface(ProviderSessionController controller, GatewayClient client) =>
    ProviderSessionSurface(
      client: client,
      controller: controller,
      provider: 'codex',
      draft: 'hello native',
      workspaceRef: 'workspace-a',
      selectedModel: 'codex:gpt-5.5',
      onProviderChanged: (_) {},
      onDraftChanged: (_) {},
    );

Map<String, dynamic> _oldCursor({bool reconcile = false}) => dispatchProgress(
      operationRef: dispatchOperationA,
      nativeThreadId: 'threadOld',
      lastProviderEventId: 'eventOld',
      phase: reconcile ? 'close_indeterminate' : 'provider_event',
      historyStatus: reconcile ? 'indeterminate' : 'complete',
      sideEffectStatus: reconcile ? 'write_uncertain' : 'input_sent',
      reason: reconcile ? 'shutdown_uncertain' : 'observed',
    );

Map<String, dynamic> _newCursor({bool reconcile = false}) => dispatchProgress(
      operationRef: dispatchOperationA,
      nativeThreadId: 'threadNew',
      lastProviderEventId: 'eventNew',
      phase: reconcile ? 'close_indeterminate' : 'provider_event',
      historyStatus: reconcile ? 'indeterminate' : 'complete',
      sideEffectStatus: reconcile ? 'write_uncertain' : 'input_sent',
      reason: reconcile ? 'shutdown_uncertain' : 'observed',
    );
