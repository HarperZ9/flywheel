import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';

Future<ByteData> _fontFile(String path) async {
  return ByteData.sublistView(await File(path).readAsBytes());
}

Future<void> _loadAppFonts() async {
  final text = FontLoader(kTextFamily)
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-regular.ttf'))
    ..addFont(_fontFile('assets/fonts/hanken-grotesk-extrabold.ttf'));
  final mono = FontLoader(kMonoFamily)
    ..addFont(_fontFile('assets/fonts/CascadiaMono.ttf'))
    ..addFont(_fontFile('assets/fonts/CascadiaMonoItalic.ttf'));
  await Future.wait([text.load(), mono.load()]);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(_loadAppFonts);

  testWidgets('Cascadia preserves dense code table and sidebar layout',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1180, 720));
    addTearDown(() async => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: flywheelLightTheme(),
      home: const Scaffold(body: _DenseFontFixture()),
    ));
    await tester.pump();

    expect(tester.takeException(), isNull);
    _expectLegibleHankenText(
      'Dense font fixture',
      tester.widget<Text>(find.byKey(const Key('hankenTitle'))).style!,
      maxWidth: 360,
    );
    _expectLegibleHankenText(
      'Code, hashes, tables, and sidebar labels use Cascadia Mono.',
      tester.widget<Text>(find.byKey(const Key('hankenSubtitle'))).style!,
      maxWidth: 600,
    );
    await expectLater(
      find.byKey(const Key('cascadiaDenseLayout')),
      matchesGoldenFile('goldens/cascadia_dense_layout.png'),
    );
  });
}

void _expectLegibleHankenText(String text, TextStyle style,
    {required double maxWidth}) {
  final painter = TextPainter(
    text: TextSpan(text: text, style: style),
    textDirection: TextDirection.ltr,
  )..layout();
  expect(painter.width, greaterThan(120));
  expect(painter.width, lessThan(maxWidth));
}

TextStyle _hanken(TextStyle? style) {
  return (style ?? const TextStyle()).copyWith(fontFamily: kTextFamily);
}

class _DenseFontFixture extends StatelessWidget {
  const _DenseFontFixture();

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return RepaintBoundary(
      key: const Key('cascadiaDenseLayout'),
      child: Container(
        color: t.ground,
        padding: const EdgeInsets.all(24),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _Sidebar(t),
            const SizedBox(width: 16),
            Expanded(child: _CodeAndTable(t)),
          ],
        ),
      ),
    );
  }
}

class _Sidebar extends StatelessWidget {
  final FwTokens t;
  const _Sidebar(this.t);

  @override
  Widget build(BuildContext context) {
    final items = ['TOOLS', 'WORLD', 'RECEIPTS', 'CODE', 'AGENT'];
    return Container(
      width: 236,
      decoration: BoxDecoration(
        color: t.panel,
        border: Border.all(color: t.line),
        borderRadius: BorderRadius.circular(14),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('FLYWHEEL', style: fwKicker(t, color: t.ink)),
          const SizedBox(height: 18),
          for (final item in items)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  Container(width: 8, height: 8, color: t.verified),
                  const SizedBox(width: 10),
                  Text(item, style: fwKicker(t, size: 9.8)),
                ],
              ),
            ),
          const Spacer(),
          Text('sha256:08026F617EEA315CACA59898784E999F6',
              style: fwMono(t, size: 11, color: t.inkMuted)),
        ],
      ),
    );
  }
}

class _CodeAndTable extends StatelessWidget {
  final FwTokens t;
  const _CodeAndTable(this.t);

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Dense font fixture',
            key: const Key('hankenTitle'),
            style: _hanken(Theme.of(context).textTheme.headlineMedium)),
        const SizedBox(height: 8),
        Text('Code, hashes, tables, and sidebar labels use Cascadia Mono.',
            key: const Key('hankenSubtitle'),
            style: _hanken(Theme.of(context).textTheme.bodyMedium)),
        const SizedBox(height: 18),
        Container(
          decoration: BoxDecoration(
            color: t.ground2,
            border: Border.all(color: t.line),
            borderRadius: BorderRadius.circular(14),
          ),
          padding: const EdgeInsets.all(16),
          child: Text(_codeSample, style: fwMono(t, size: 12.2)),
        ),
        const SizedBox(height: 16),
        _DenseTable(t),
      ],
    );
  }
}

class _DenseTable extends StatelessWidget {
  final FwTokens t;
  const _DenseTable(this.t);

  @override
  Widget build(BuildContext context) {
    final rows = [
      ['lane', 'status', 'receipt', 'age'],
      ['index', 'verified', '4ca80ac105e80a58', '00:03'],
      ['gather', 'drift', 'd9d23dfb03c68444', '13:44'],
      ['forum', 'unverifiable', '08026f617eea315c', 'n/a'],
      ['relay', 'verified', '8a6c38796c7ea332', '01:18'],
    ];
    return Table(
      columnWidths: const {
        0: FixedColumnWidth(116),
        1: FixedColumnWidth(136),
        2: FlexColumnWidth(),
        3: FixedColumnWidth(72),
      },
      border: TableBorder.all(color: t.hairline),
      children: [
        for (var i = 0; i < rows.length; i++)
          TableRow(
            decoration: BoxDecoration(color: i == 0 ? t.panel : t.ground),
            children: [
              for (final cell in rows[i])
                Padding(
                  padding: const EdgeInsets.all(9),
                  child: Text(
                    cell,
                    style: i == 0
                        ? fwKicker(t, size: 9.8, color: t.ink)
                        : fwMono(t, size: 12),
                  ),
                ),
            ],
          ),
      ],
    );
  }
}

const _codeSample = '''
final proof = verify(sourceTree, policy);
if (proof.state == Verdict.drift) {
  return Receipt.unverifiable('payload hash moved');
}
// tabular figures: 0123456789 000111222333444555
sha256: d5e2dc1121fb6dd0bfa8d6a476f06a0170d62e7ed68b728
''';
