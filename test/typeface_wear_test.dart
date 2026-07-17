// Live-wear must be a real handoff: the Wear button appears only when the
// mint carries its font file, the loader receives the decoded bytes under
// a family named by the mint id, and the preview then renders with that
// family. A refused or ttf-less mint offers nothing to wear.
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/typeface_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Map<String, dynamic> _face({bool ttf = true}) => {
      'refused': false,
      'refusals': [],
      'glyphs': {
        'a': {
          'advance': 500.0,
          'contours': [
            [
              [0.0, 0.0],
              [400.0, 0.0],
              [400.0, 400.0],
              [0.0, 400.0],
              [0.0, 0.0],
            ]
          ],
        },
      },
      'metrics': {'x_height': 500.0},
      'receipt': {'mint_id': 'abcd1234abcd1234'},
      if (ttf) 'ttf_b64': base64Encode([1, 2, 3, 4]),
      if (ttf) 'ttf_family': 'Zentropy Mint 58',
    };

void main() {
  testWidgets('wear loads the minted bytes under the mint-id family',
      (tester) async {
    String? loadedFamily;
    Uint8List? loadedBytes;
    await tester.pumpWidget(_wrap(TypefacePanel(
      onMint: (params, seed) async => _face(),
      fontLoad: (family, bytes) async {
        loadedFamily = family;
        loadedBytes = bytes;
      },
    )));
    await tester.ensureVisible(find.text('Mint'));
    await tester.tap(find.text('Mint'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Wear it'));
    await tester.tap(find.text('Wear it'));
    await tester.pumpAndSettle();
    expect(loadedFamily, 'ZentropyMint-abcd1234abcd1234');
    expect(loadedBytes, [1, 2, 3, 4]);
    expect(find.text('WEARING IT'), findsOneWidget);
    final field = tester.widget<TextField>(
        find.widgetWithText(TextField,
            'the quick brown fox jumps over the lazy dog 0123456789'));
    expect(field.style?.fontFamily, 'ZentropyMint-abcd1234abcd1234');
  });

  testWidgets('a mint without a font file offers nothing to wear',
      (tester) async {
    await tester.pumpWidget(_wrap(TypefacePanel(
      onMint: (params, seed) async => _face(ttf: false),
      fontLoad: (family, bytes) async {},
    )));
    await tester.ensureVisible(find.text('Mint'));
    await tester.tap(find.text('Mint'));
    await tester.pumpAndSettle();
    expect(find.text('MINTED'), findsOneWidget);
    expect(find.text('Wear it'), findsNothing);
  });
}
