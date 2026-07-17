// flywheel_nav.dart — the de-silo seam. Any view can ask the shell to jump
// to another destination and hand it a payload, so an entity shown in one
// tool (a lane, a receipt id, a file path, a provider) is a doorway into
// the tool that owns it. One InheritedWidget, no state-management dep.

import 'package:flutter/widgets.dart';

/// A request to open another destination, optionally carrying an argument
/// the target view consumes on arrival (an eid to open, a path to load).
class NavIntent {
  final String label;
  final Object? arg;
  const NavIntent(this.label, {this.arg});
}

class FlywheelNav extends InheritedWidget {
  final void Function(String label, {Object? arg}) goTo;
  const FlywheelNav({super.key, required this.goTo, required super.child});

  static FlywheelNav? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<FlywheelNav>();

  /// Convenience: jump if the seam is present, otherwise no-op (so a widget
  /// used in a test or outside the shell never crashes).
  static void jump(BuildContext context, String label, {Object? arg}) =>
      of(context)?.goTo(label, arg: arg);

  @override
  bool updateShouldNotify(FlywheelNav old) => false;
}
