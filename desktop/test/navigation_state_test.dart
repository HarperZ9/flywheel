// View-state retention: a destination's scroll position survives leaving
// and returning, because each destination's subtree lives in a stable
// PageStorage bucket keyed by route id.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/view_cache.dart';

void main() {
  Widget scrollableDestination(Key key) => ListView(
        key: key,
        children: [
          for (var i = 0; i < 60; i++)
            SizedBox(height: 40, child: Text('row $i')),
        ],
      );

  testWidgets('scroll offset survives switching away and back',
      (tester) async {
    tester.view.physicalSize = const Size(400, 300);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final cache = ViewCache();
    const receipts =
        AppLocation(routeId: DestinationId.receipts);
    const plan = AppLocation(routeId: DestinationId.plan);
    var current = receipts;

    Widget shell() => MaterialApp(
          home: Scaffold(
            body: Column(children: [
              Expanded(
                child: cache.viewFor(current,
                    (_) => scrollableDestination(Key('list-${current.routeId.name}'))),
              ),
              Row(children: [
                ElevatedButton(
                    onPressed: () => current = receipts,
                    child: const Text('to receipts')),
                ElevatedButton(
                    onPressed: () => current = plan,
                    child: const Text('to plan')),
              ]),
            ]),
          ),
        );

    await tester.pumpWidget(shell());
    // Scroll the receipts list down.
    await tester.drag(find.text('row 0'), const Offset(0, -400));
    await tester.pump();
    final scrolledOffset =
        tester.state<ScrollableState>(find.byType(Scrollable).first)
            .position
            .pixels;
    expect(scrolledOffset, greaterThan(0));

    // Switch to plan and back; the receipts scroll offset is restored.
    await tester.tap(find.text('to plan'));
    await tester.pump();
    expect(find.text('to plan'), findsOneWidget);
    await tester.tap(find.text('to receipts'));
    await tester.pump();
    final restored =
        tester.state<ScrollableState>(find.byType(Scrollable).first)
            .position
            .pixels;
    expect(restored, scrolledOffset,
        reason: 'the bucket restores view-local scroll per route id');
  });

  test('cache keys are stable per route id', () {
    final cache = ViewCache();
    const a = AppLocation(routeId: DestinationId.receipts);
    const b = AppLocation(routeId: DestinationId.receipts);
    expect(cache.keyFor(a), cache.keyFor(b));
    expect(cache.keyFor(a),
        isNot(cache.keyFor(const AppLocation(routeId: DestinationId.plan))));
  });
}
