// The phone's bottom bar shows the first-run destinations plus More, marks the
// selected one, routes a tap to its id, and opens the full catalog from More.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/accessibility/accessible_action.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/destination_catalog.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/mobile_nav_bar.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: child),
    );

MobileNavBar _bar({
  DestinationId selected = DestinationId.chat,
  ValueChanged<DestinationId>? onGo,
  VoidCallback? onMore,
}) =>
    MobileNavBar(
      primaries: mobilePrimaryDestinations,
      selected: selected,
      onGo: onGo ?? (_) {},
      onMore: onMore ?? () {},
    );

void main() {
  testWidgets('shows the four first-run destinations and More', (tester) async {
    await tester.pumpWidget(_wrap(_bar()));
    for (final label in const ['Journey', 'Chat', 'Companion', 'Receipts']) {
      expect(find.text(label), findsOneWidget);
    }
    expect(find.text('More'), findsOneWidget);
    expect(mobilePrimaryDestinations, hasLength(4),
        reason: 'four primaries keep the bar readable on a phone');
  });

  testWidgets('marks exactly the selected destination', (tester) async {
    await tester.pumpWidget(_wrap(_bar(selected: DestinationId.receipts)));
    final selected =
        find.byWidgetPredicate((w) => w is AccessibleAction && w.selected);
    expect(selected, findsOneWidget);
    expect(tester.widget<AccessibleAction>(selected).semanticLabel, 'Receipts');
  });

  testWidgets('a tap routes to that destination id', (tester) async {
    DestinationId? went;
    await tester.pumpWidget(_wrap(_bar(onGo: (id) => went = id)));
    await tester.tap(find.text('Companion'));
    expect(went, DestinationId.companion);
  });

  testWidgets('More opens the full catalog and is not a destination',
      (tester) async {
    var moreTapped = false;
    DestinationId? went;
    await tester.pumpWidget(_wrap(
        _bar(onGo: (id) => went = id, onMore: () => moreTapped = true)));
    await tester.tap(find.text('More'));
    expect(moreTapped, isTrue);
    expect(went, isNull, reason: 'More is not a route');
  });
}
