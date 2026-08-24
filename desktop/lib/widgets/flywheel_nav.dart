// flywheel_nav.dart — the de-silo seam. Any view can ask the shell to jump
// to another destination and hand it an opaque public ref, so an entity
// shown in one tool (a receipt hash, an operation, a journey) is a doorway
// into the tool that owns it. Routing is by stable id, never by label.
// One InheritedWidget, no state-management dep.

import 'package:flutter/widgets.dart';

import '../navigation/app_route.dart';

/// A request to open another destination, optionally carrying an opaque
/// public ref the target view consumes on arrival.
class NavIntent {
  final DestinationId routeId;
  final Object? arg;
  const NavIntent(this.routeId, {this.arg});
}

class FlywheelNav extends InheritedWidget {
  final void Function(DestinationId routeId, {Object? arg}) goTo;
  const FlywheelNav({super.key, required this.goTo, required super.child});

  static FlywheelNav? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<FlywheelNav>();

  /// Convenience: jump if the seam is present, otherwise no-op (so a widget
  /// used in a test or outside the shell never crashes).
  static void jump(BuildContext context, DestinationId routeId,
          {Object? arg}) =>
      of(context)?.goTo(routeId, arg: arg);

  @override
  bool updateShouldNotify(FlywheelNav old) => false;
}
