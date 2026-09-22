import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/controllers/provider_session_controller.dart';
import 'package:flywheel_desktop/widgets/provider_session_pane.dart';

const _sha = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _op = 'op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

void main() {
  testWidgets('provider session pane shows recovery boundary and controls',
      (tester) async {
    // Break this catches: the native-session UI hides an uncertain provider
    // write behind a normal ready state.
    final controller = ProviderSessionController()..begin(_op);
    addTearDown(controller.dispose);
    controller.acceptProgress({
      'provider_session': {
        'phase': 'close_indeterminate',
        'provider': 'codex',
        'operation_ref': _op,
        'native_thread_id': 'thread-1',
        'history_status': 'indeterminate',
        'side_effect_status': 'unknown_after_send',
        'config_digest': _sha,
      },
    });

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ProviderSessionPane(
          controller: controller,
          onReconcile: () {},
        ),
      ),
    ));

    expect(find.text('Provider native session'), findsOneWidget);
    expect(find.text('provider: codex'), findsOneWidget);
    expect(find.text('thread: thread-1'), findsOneWidget);
    expect(find.text('Reconcile before sending another turn.'), findsOneWidget);
    expect(
        tester
            .widget<ElevatedButton>(
                find.widgetWithText(ElevatedButton, 'Send turn'))
            .enabled,
        isFalse);
    expect(
        tester
            .widget<OutlinedButton>(
                find.widgetWithText(OutlinedButton, 'Reconcile'))
            .enabled,
        isTrue);
  });
}
