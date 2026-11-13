// What a destination is, kept apart from which destinations exist. Labels are
// presentation; DestinationId remains the routing contract when a label
// changes. The catalog re-exports both names, so importing the catalog is
// still enough.
import 'app_route.dart';

enum DestinationGroup { work, chat, code, evidence, advanced }

class DestinationSpec {
  final DestinationId id;
  final String label;
  final String abbr;
  final DestinationGroup group;

  /// Phone primary destinations appear in the bottom bar; the rest are in More.
  final bool mobilePrimary;
  const DestinationSpec(
    this.id,
    this.label, {
    required this.abbr,
    required this.group,
    this.mobilePrimary = false,
  });
}
