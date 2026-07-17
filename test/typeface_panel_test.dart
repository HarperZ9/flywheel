// The forge's front does what the engine promises: a mint renders the
// specimen and its receipt, and a refusal names its rule instead of
// drawing an illegible face.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/typeface_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('a mint renders the receipt and the specimen painter',
      (tester) async {
    Map<String, dynamic>? gotParams;
    int? gotSeed;
    await tester.pumpWidget(_wrap(TypefacePanel(
      onMint: (params, seed) async {
        gotParams = params;
        gotSeed = seed;
        return {
          'refused': false,
          'refusals': [],
          'receipt': {'mint_id': 'abcd1234abcd1234'},
          'metrics': {'x_height': 500.0},
          'glyphs': {
            'a': {
              'advance': 600.0,
              'contours': [
                [
                  [0.0, 0.0],
                  [100.0, 0.0],
                  [100.0, 500.0],
                  [0.0, 500.0],
                  [0.0, 0.0]
                ]
              ],
            },
          },
        };
      },
    )));
    await tester.tap(find.text('Mint'));
    await tester.pumpAndSettle();
    expect(gotSeed, 58);
    expect(gotParams!['weight'], closeTo(0.085, 1e-9));
    expect(find.text('MINTED'), findsOneWidget);
    expect(find.textContaining('abcd1234'), findsOneWidget);
    expect(find.byType(CustomPaint), findsWidgets);
  });

  testWidgets('a refusal names its rule instead of drawing', (tester) async {
    await tester.pumpWidget(_wrap(TypefacePanel(
      onMint: (params, seed) async => {
        'refused': true,
        'refusals': ['counter-minimum: bowl counter 40 under 150 em-units'],
        'receipt': {'mint_id': 'ffff0000ffff0000'},
        'glyphs': {},
      },
    )));
    await tester.tap(find.text('Mint'));
    await tester.pumpAndSettle();
    expect(find.textContaining('counter-minimum'), findsOneWidget);
    expect(find.text('MINTED'), findsNothing);
  });
}
