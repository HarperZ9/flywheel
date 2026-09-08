import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/destination_catalog.dart';

void main() {
  test('approvals inbox is a stable mobile primary work destination', () {
    final spec = specFor(DestinationId.approvals);
    expect(spec, isNotNull);
    expect(spec!.label, 'Approvals');
    expect(spec.group, DestinationGroup.work);
    expect(spec.mobilePrimary, isTrue);
    expect(mobilePrimaryDestinations.map((d) => d.id),
        contains(DestinationId.approvals));
  });
}
