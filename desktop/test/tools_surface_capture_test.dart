import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/destination_catalog.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/lanes_view.dart';
import 'package:flywheel_desktop/widgets/mobile_nav_bar.dart';
import 'package:flywheel_desktop/widgets/nav_group.dart';
import 'package:flywheel_desktop/widgets/shell_rail.dart';
import 'package:http/http.dart' as http;

Future<ByteData> _fontFile(String path) async {
  return ByteData.sublistView(await File(path).readAsBytes());
}

String _captureTextFamily = kTextFamily;
String _captureFontNote = 'Production app text font assets loaded.';

Future<void> _loadAppFonts() async {
  final text = FontLoader(kTextFamily)
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-regular.ttf'))
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-semibold.ttf'))
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-bold.ttf'));
  final mono = FontLoader(kMonoFamily)
    ..addFont(_fontFile('assets/fonts/CascadiaMono.ttf'))
    ..addFont(_fontFile('assets/fonts/CascadiaMonoItalic.ttf'));
  await Future.wait([text.load(), mono.load()]);
  final windowsFonts = [
    File(r'C:\Windows\Fonts\arial.ttf'),
    File(r'C:\Windows\Fonts\arialbd.ttf'),
    File(r'C:\Windows\Fonts\ariali.ttf'),
  ];
  if (Platform.isWindows && windowsFonts.every((file) => file.existsSync())) {
    final captureText = FontLoader('Capture Sans');
    for (final file in windowsFonts) {
      captureText.addFont(_fontFile(file.path));
    }
    await captureText.load();
    _captureTextFamily = 'Capture Sans';
    _captureFontNote =
        'Capture Sans from Windows Arial, used only in this capture harness because Hanken rasterizes as block glyphs in the widget-test PNG output on this host; production theme code remains unchanged.';
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(_loadAppFonts);

  testWidgets('captures fixture Tools surface in wide and narrow layouts', (
    tester,
  ) async {
    final output = Platform.environment['TOOLS_CAPTURE_DIR'];
    final frames = <Map<String, Object>>[];
    final client = GatewayClient(
      baseUrl: 'http://fixture.invalid',
      httpClient: _FixtureHttpClient(),
    );
    addTearDown(client.close);

    await _setSurface(tester, const Size(1366, 900));
    var key = GlobalKey();
    await tester.pumpWidget(_fixtureApp(key: key, client: client, wide: true));
    await tester.pump(const Duration(milliseconds: 200));
    expect(
        find.text('VISUAL QA FIXTURE - not live gateway data'), findsOneWidget);
    expect(find.text('Tools'), findsWidgets);
    expect(find.text('Advanced lane calls'), findsOneWidget);
    expect(find.text('Install'), findsNothing);
    await _capture(tester, key, 'wide-shell-tools-fixture', output, frames);

    await _setSurface(tester, const Size(390, 844));
    key = GlobalKey();
    await tester.pumpWidget(_fixtureApp(key: key, client: client, wide: false));
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('More'), findsOneWidget);
    await tester.tap(find.text('Bulletin'));
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.textContaining('Declared by the registry'), findsOneWidget);
    await _capture(tester, key, 'narrow-tools-detail-fixture', output, frames);

    final semantics = tester.ensureSemantics();
    expect(find.bySemanticsLabel('Probe now'), findsOneWidget);
    expect(find.text('More'), findsOneWidget);
    semantics.dispose();

    if (output != null) {
      File('$output/capture.json').writeAsStringSync(
        const JsonEncoder.withIndent('  ').convert({
          'backend':
              'Flutter widget test engine / RenderRepaintBoundary.toImage',
          'fixture': 'explicit test lane roster; not live gateway data',
          'capture_text_font': _captureFontNote,
          'does_not_prove':
              'installed build behavior, device performance, production gateway data, or mobile device pixel parity',
          'checks': [
            'wide shell renders Tools selected with folded secondary navigation',
            'narrow layout renders Tools content with More route access',
            'lane details expand without public Install actions',
            'Probe now and More expose semantics labels',
          ],
          'frames': frames,
        }),
      );
    }
  });

  testWidgets('folded secondary navigation expands from keyboard focus', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    var selected = DestinationId.journey;
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: SizedBox(
          width: 240,
          child: StatefulBuilder(builder: (context, setState) {
            return NavGroup(
              label: 'Tools & admin',
              destinations: [specFor(DestinationId.plugins)!],
              selected: selected,
              collapsed: false,
              foldable: true,
              initiallyFolded: true,
              onSelect: (id) => setState(() => selected = id),
            );
          }),
        ),
      ),
    ));
    await tester.pump();
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Semantics &&
            widget.properties.label == 'Expand Tools & admin group',
      ),
      findsOneWidget,
    );
    expect(find.text('Plugins'), findsNothing);

    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text('Plugins'), findsOneWidget);
    semantics.dispose();
  });
}

Widget _fixtureApp({
  required GlobalKey key,
  required GatewayClient client,
  required bool wide,
}) {
  final tools = LanesView(
    roster: _fixtureRoster,
    alive: true,
    onProbe: () {},
    client: client,
  );
  final body = wide
      ? Row(children: [
          SizedBox(
            width: 260,
            child: ShellRail(
              collapsed: false,
              width: 248,
              selected: DestinationId.lanes,
              onGo: (_) {},
              onResize: (_) {},
              onToggleCollapse: () {},
              onToggleTheme: () {},
              onOpenAppearance: () {},
              onOpenRecovery: () {},
            ),
          ),
          Expanded(
              child: Column(children: [_banner(), Expanded(child: tools)])),
        ])
      : Column(children: [_banner(), Expanded(child: tools)]);
  return MaterialApp(
    theme: flywheelLightTheme(textFamily: _captureTextFamily),
    home: RepaintBoundary(
      key: key,
      child: Scaffold(
        body: body,
        bottomNavigationBar: wide
            ? null
            : MobileNavBar(
                primaries: mobilePrimaryDestinations,
                selected: DestinationId.lanes,
                onGo: (_) {},
                onMore: () {},
              ),
      ),
    ),
  );
}

Widget _banner() => Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: const Color(0xFFF2E7D5),
      child: const Text(
        'VISUAL QA FIXTURE - not live gateway data',
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
      ),
    );

final _fixtureRoster = LaneRoster(
  nLanes: 4,
  byStatus: const {'live': 1, 'declared': 1, 'missing': 1, 'stale': 1},
  allLive: false,
  lanes: [
    Lane(
      name: 'flywheel',
      kind: 'bundled',
      installedVersion: 'fixture-0.6.2',
      expectedVersion: 'fixture-0.6.2',
      status: 'live',
      organ: 'runtime',
      role: 'engine shell',
      detail: 'Fixture live lane with two callable tools.',
      tools: 2,
    ),
    Lane(
      name: 'bulletin',
      kind: 'http',
      expectedVersion: 'fixture-remote',
      status: 'declared',
      organ: 'correspondence',
      role: 'open board',
      detail:
          'Fixture declared lane; run Probe now to verify endpoint reachability.',
    ),
    Lane(
      name: 'mneme',
      kind: 'pip',
      expectedVersion: 'fixture-0.2.0',
      status: 'missing',
      organ: 'memory',
      role: 'receipt-backed recall',
      detail:
          'Fixture missing lane; no reviewed native setup action is exposed.',
      packageInstallable: false,
    ),
    Lane(
      name: 'plexus',
      kind: 'pip',
      installedVersion: 'fixture-0.1.0',
      expectedVersion: 'fixture-0.2.0',
      status: 'stale',
      organ: 'orchestration',
      role: 'agent mesh',
      detail: 'Fixture stale lane; repair remains a reviewed backend concern.',
      tools: 1,
    ),
  ],
);

Future<void> _setSurface(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Future<void> _capture(
  WidgetTester tester,
  GlobalKey key,
  String name,
  String? output,
  List<Map<String, Object>> frames,
) async {
  final boundary =
      key.currentContext!.findRenderObject() as RenderRepaintBoundary;
  await tester.runAsync(() async {
    final image = await boundary.toImage();
    final png = (await image.toByteData(format: ui.ImageByteFormat.png))!
        .buffer
        .asUint8List();
    final frame = <String, Object>{
      'name': name,
      'width': image.width,
      'height': image.height,
      'png_sha256': sha256.convert(png).toString(),
    };
    if (output != null) {
      final file = File('$output/$name.png');
      file.parent.createSync(recursive: true);
      file.writeAsBytesSync(png);
      frame['path'] = file.path;
    }
    frames.add(frame);
    image.dispose();
  });
}

class _FixtureHttpClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final body = switch (request.url.path) {
      '/api/lanes/callable' => {
          'lanes': [
            {
              'name': 'flywheel',
              'description': 'Fixture callable status tool.',
              'min_tier': 'T1',
              'organ': 'runtime',
            },
            {
              'name': 'plexus',
              'description': 'Fixture advanced mesh diagnostic.',
              'min_tier': 'T2',
              'unlisted_tool_tier': 'T3',
              'organ': 'orchestration',
            },
          ],
        },
      _ => <String, Object?>{},
    };
    return http.StreamedResponse(
      Stream.value(utf8.encode(jsonEncode(body))),
      200,
      headers: {'content-type': 'application/json'},
    );
  }
}
