import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/services/client_connection_preview.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/client_connection_panel.dart';
import 'package:flywheel_desktop/views/plugins_view.dart';
import 'package:http/testing.dart';
import 'package:http/http.dart' as http;

void main() {
  const path = r'C:\Program Files\Flywheel\engine\flywheel-gateway.exe';
  final clipboard = <MethodCall>[];

  setUp(() {
    clipboard.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') clipboard.add(call);
      return null;
    });
  });
  tearDown(() => TestDefaultBinaryMessengerBinding
      .instance.defaultBinaryMessenger
      .setMockMethodCallHandler(SystemChannels.platform, null));

  Future<void> mount(WidgetTester tester, String? engine,
      {double width = 800, double scale = 1}) async {
    await tester.binding.setSurfaceSize(Size(width, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: MediaQuery(
        data: MediaQueryData(textScaler: TextScaler.linear(scale)),
        child: Scaffold(
            body: SingleChildScrollView(
          child: ClientConnectionPanel(
            preview: ClientConnectionPreview.fromBundledEngine(engine),
          ),
        )),
      ),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('unavailable engine explains recovery and disables copying',
      (tester) async {
    await mount(tester, null);
    expect(
        find.textContaining('bundled engine is unavailable'), findsOneWidget);
    final button = tester.widget<OutlinedButton>(
        find.widgetWithText(OutlinedButton, 'Copy configuration'));
    expect(button.onPressed, isNull);
    expect(find.byType(SelectableText), findsNothing);
    expect(clipboard, isEmpty);
  });

  testWidgets('only explicit copy writes selected format to fake clipboard',
      (tester) async {
    await mount(tester, path);
    expect(find.textContaining('Connection not tested'), findsOneWidget);
    expect(clipboard, isEmpty);
    await tester.tap(find.text('MCP JSON'));
    await tester.pumpAndSettle();
    expect(clipboard, isEmpty);
    await tester.tap(find.text('Copy configuration'));
    await tester.pumpAndSettle();
    expect(clipboard, hasLength(1));
    expect(clipboard.single.arguments, {
      'text': ClientConnectionPreview.fromBundledEngine(path)
          .snippet(ClientConfigFormat.mcpJson),
    });
    expect(find.text('Configuration copied. Connection not tested.'),
        findsOneWidget);
  });

  testWidgets('narrow large-text layout keeps labelled controls accessible',
      (tester) async {
    final semantics = tester.ensureSemantics();
    await mount(tester, path, width: 360, scale: 2);
    expect(tester.takeException(), isNull);
    expect(find.bySemanticsLabel('Copy configuration'), findsOneWidget);
    expect(find.bySemanticsLabel('Codex (TOML)'), findsOneWidget);
    expect(
        find.textContaining('No model or publisher service'), findsOneWidget);
    await tester.ensureVisible(find.text('Copy configuration'));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    semantics.dispose();
  });

  testWidgets('clipboard failure remains visible and permits a retry',
      (tester) async {
    await mount(tester, path);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        throw PlatformException(code: 'unavailable');
      }
      return null;
    });
    await tester.tap(find.text('Copy configuration'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Could not copy.'), findsOneWidget);
    expect(
        tester
            .widget<OutlinedButton>(
                find.widgetWithText(OutlinedButton, 'Copy configuration'))
            .onPressed,
        isNotNull);
  });

  testWidgets('Plugins exposes local preview while gateway is offline',
      (tester) async {
    var requests = 0;
    final client = GatewayClient(httpClient: MockClient((_) async {
      requests++;
      throw StateError('Preview must not call the gateway');
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: PluginsView(client: client, alive: false))));
    await tester.pumpAndSettle();
    expect(find.byType(ClientConnectionPanel), findsNothing);
    await tester.tap(find.text('Connect a local client'));
    await tester.pumpAndSettle();
    expect(find.byType(ClientConnectionPanel), findsOneWidget);
    expect(requests, 0);
    expect(clipboard, isEmpty);
  });

  testWidgets('connection preview preserves registration in normal viewport',
      (tester) async {
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response(
            '{"plugins":[],"entries":[],"rows":[],"summary":{}}', 200)));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: PluginsView(client: client, alive: true))));
    await tester.pumpAndSettle();
    expect(find.text('Register').hitTestable(), findsOneWidget);
    await tester.enterText(find.byType(TextField).first, 'preserved');
    await tester.tap(find.text('Connect a local client'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(clipboard, isEmpty);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.text('Register').hitTestable(), findsOneWidget);
    expect(find.text('preserved'), findsOneWidget);
  });

  testWidgets('preview dialog scrolls at narrow width and large text',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(360, 600));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context)
                .copyWith(textScaler: TextScaler.linear(2)),
            child: child!),
        home: Scaffold(
            body: ClientConnectionAction(
                preview: ClientConnectionPreview.fromBundledEngine(path)))));
    await tester.tap(find.text('Connect a local client'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.text('Copy configuration'));
    expect(find.text('Copy configuration').hitTestable(), findsOneWidget);
    expect(find.text('Close').hitTestable(), findsOneWidget);
    expect(clipboard, isEmpty);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
    expect(find.byType(ClientConnectionPanel), findsNothing);
  });
}
