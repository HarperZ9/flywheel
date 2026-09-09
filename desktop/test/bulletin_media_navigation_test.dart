import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/navigation/destination_catalog.dart';

void main() {
  test('bulletin destination is reachable from the work catalog', () {
    final spec = specFor(DestinationId.bulletin)!;
    expect(spec.label, 'Bulletin');
    expect(spec.group, DestinationGroup.work);
    expect(
        destinationCatalog.map((d) => d.id), contains(DestinationId.bulletin));
  });
}
