// Deep links carry only stable route ids and opaque public refs. Paths,
// hosts, unknown query keys, and non-opaque refs are rejected, typed.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/navigation/app_route.dart';

void main() {
  test('a plain destination link parses', () {
    final loc = parseDeepLink(Uri.parse('flywheel://dest/receipts'));
    expect(loc, isNotNull);
    expect(loc!.routeId, DestinationId.receipts);
    expect(loc.selectionRef, isNull);
  });

  test('a link may carry one opaque public ref', () {
    final loc = parseDeepLink(
        Uri.parse('flywheel://dest/journey?ref=jrn_${'a' * 32}'));
    expect(loc!.journeyRef, 'jrn_${'a' * 32}');
  });

  test('unknown scheme or host is rejected', () {
    expect(parseDeepLink(Uri.parse('https://dest/receipts')), isNull);
    expect(parseDeepLink(Uri.parse('flywheel://other/receipts')), isNull);
  });

  test('extra path segments are rejected', () {
    expect(
        parseDeepLink(Uri.parse('flywheel://dest/receipts/extra')), isNull);
    expect(parseDeepLink(Uri.parse('flywheel://dest/')), isNull);
  });

  test('an unknown route id is rejected', () {
    expect(parseDeepLink(Uri.parse('flywheel://dest/not-a-route')), isNull);
  });

  test('unknown query keys are rejected', () {
    expect(
        parseDeepLink(Uri.parse(
            'flywheel://dest/receipts?ref=rcpt_${'a' * 32}&path=C:\\x')),
        isNull);
  });

  test('non-opaque or malformed refs are rejected', () {
    expect(parseDeepLink(Uri.parse('flywheel://dest/receipts?ref=abc')),
        isNull);
    expect(
        parseDeepLink(
            Uri.parse('flywheel://dest/receipts?ref=../etc/passwd')),
        isNull);
    expect(
        parseDeepLink(
            Uri.parse('flywheel://dest/receipts?ref=jrn_${'z' * 40}')),
        isNull,
        reason: 'refs are exactly typed; longer hex is not a public ref');
  });

  test('a journey ref on a non-journey destination is rejected', () {
    expect(
        parseDeepLink(
            Uri.parse('flywheel://dest/receipts?ref=jrn_${'a' * 32}')),
        isNull,
        reason: 'journey refs bind to the journey destination only');
  });
}
