import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/chat_header.dart';
import 'package:flywheel_desktop/widgets/chat_thread.dart';
import 'package:flywheel_desktop/widgets/chat_welcome.dart';
import 'package:flywheel_desktop/widgets/rowan_avatar.dart';

Widget host(Widget child) =>
    MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: child));

void main() {
  testWidgets(
      'short welcome keeps starters reachable without clipping companion',
      (tester) async {
    tester.view.physicalSize = const Size(320, 220);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    String? selected;
    await tester
        .pumpWidget(host(ChatWelcome(onStarter: (text) => selected = text)));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.byType(ActionChip).last);
    await tester.pumpAndSettle();
    await tester.tap(find.byType(ActionChip).last);
    expect(selected, isNotEmpty);
  });

  testWidgets('chat welcome introduces the same static Rowan companion',
      (tester) async {
    await tester.pumpWidget(host(const ChatWelcome()));
    await tester.pumpAndSettle();
    expect(find.byType(RowanAvatar), findsOneWidget);
    expect(find.text("I'm Rowan."), findsOneWidget);
    expect(find.byIcon(Icons.auto_awesome_outlined), findsNothing);
  });

  testWidgets('assistant identity does not change with receipt state or user',
      (tester) async {
    final controller = ScrollController();
    await tester.pumpWidget(host(ChatThread(controller: controller, messages: [
      ChatMessage(role: 'user', text: 'My request'),
      ChatMessage(role: 'assistant', text: 'Unchecked reply'),
      ChatMessage(
          role: 'assistant',
          text: 'Checked reply',
          receipt: {'id': 'checked'},
          receiptState: ReceiptState.match),
    ])));
    await tester.pumpAndSettle();
    expect(find.byType(RowanAvatar), findsNWidgets(2));
    expect(find.text('Y'), findsOneWidget);
    expect(find.text('MATCH'), findsOneWidget);
    expect(find.text('missing'), findsOneWidget);
    for (final avatar
        in tester.widgetList<RowanAvatar>(find.byType(RowanAvatar))) {
      expect(avatar.pose.uniforms, [0, 0, 0, 0]);
    }
    expect(find.byType(Image), findsNothing);
    await tester.pumpWidget(const SizedBox());
    controller.dispose();
  });

  testWidgets('narrow header preserves provider selection beside Rowan',
      (tester) async {
    tester.view.physicalSize = const Size(320, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var conversations = 0;
    bool? selectedMode;
    await tester.pumpWidget(host(ChatHeader(
        agentMode: false,
        streaming: false,
        endpoints: [
          EndpointRow(
              name: 'local-model',
              backend: 'local',
              credential: 'local-none',
              providerRole: 'local',
              configured: true)
        ],
        endpoint: 'local-model',
        chosenModel: null,
        onMode: (value) => selectedMode = value,
        onEndpoint: (_) {},
        onModel: (_) {},
        loadModels: () async => {},
        onShowConversations: () => conversations++)));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byType(RowanAvatar), findsOneWidget);
    expect(find.text('local-model'), findsOneWidget);
    await tester.tap(find.byTooltip('Conversations'));
    await tester.tap(find.text('agent'));
    expect(conversations, 1);
    expect(selectedMode, isTrue);
  });
}
