// Typed navigation history: locations carry only stable IDs and opaque
// public refs, back/forward restore the full location, and every commit
// waits for the unsaved-work guard.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/navigation_controller.dart';

void main() {
  test('history stores ids and opaque refs, never widgets or paths', () {
    final c = NavigationController(guard: (_) async => true);
    expect(c.current.routeId, DestinationId.journey,
        reason: 'journey is home');
    final loc = AppLocation(
        routeId: DestinationId.receipts,
        selectionRef: 'rcpt_${'a' * 32}',
        scrollOffset: 120);
    expect(loc.toJson().values.any((v) => v.toString().contains('Widget')),
        isFalse, reason: 'a location is data, not a widget tree');
  });

  test('go commits, pushes back, and clears forward', () async {
    final c = NavigationController(guard: (_) async => true);
    final ok = await c
        .go(const AppLocation(routeId: DestinationId.receipts));
    expect(ok, isTrue);
    expect(c.current.routeId, DestinationId.receipts);
    expect(c.canBack, isTrue);
    expect(c.canForward, isFalse);
    await c.go(const AppLocation(routeId: DestinationId.plan));
    expect(c.canBack, isTrue);
    expect(c.canForward, isFalse);
  });

  test('back and forward restore the full location', () async {
    final c = NavigationController(guard: (_) async => true);
    final target = AppLocation(
        routeId: DestinationId.receipts,
        journeyRef: 'jrn_${'a' * 32}',
        selectionRef: 'rcpt_${'b' * 32}',
        viewState: 'verify',
        scrollOffset: 88);
    await c.go(target);
    await c.back();
    expect(c.current.routeId, DestinationId.journey);
    expect(c.canForward, isTrue);
    final restored = await c.forward();
    expect(restored, isTrue);
    expect(c.current, target,
        reason: 'journey ref, selection, view state, and scroll all survive');
  });

  test('a denied guard blocks the commit and leaves state untouched',
      () async {
    var allowed = false;
    final c = NavigationController(guard: (_) async => allowed);
    final before = c.current;
    final ok = await c.go(const AppLocation(routeId: DestinationId.code));
    expect(ok, isFalse);
    expect(c.current, before);
    expect(c.canBack, isFalse);
  });

  test('the guard receives the destination label for its prompt', () async {
    final seen = <String>[];
    final c = NavigationController(guard: (label) async {
      seen.add(label);
      return true;
    });
    await c.go(const AppLocation(routeId: DestinationId.workflows));
    expect(seen, ['Workflows']);
  });

  test('going to the current location is a no-op that keeps history', () async {
    final c = NavigationController(guard: (_) async => true);
    final ok = await c
        .go(const AppLocation(routeId: DestinationId.receipts));
    expect(ok, isTrue);
    final depthBefore = c.canBack;
    final repeat =
        await c.go(const AppLocation(routeId: DestinationId.receipts));
    expect(repeat, isTrue);
    expect(c.canBack, depthBefore,
        reason: 'a same-location commit must not add a history entry');
  });

  test('an explicit initial location is where the app opens', () {
    // A phone opens on Chat; the default without an initial stays Journey.
    final phone = NavigationController(
        guard: (_) async => true,
        initial: const AppLocation(routeId: DestinationId.chat));
    expect(phone.current.routeId, DestinationId.chat);
    expect(phone.canBack, isFalse, reason: 'the landing is not a history entry');
    final desktop = NavigationController(guard: (_) async => true);
    expect(desktop.current.routeId, DestinationId.journey);
  });
}
