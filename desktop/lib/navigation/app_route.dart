// app_route.dart -- stable typed locations for the desktop shell.
//
// A location carries a stable route id plus opaque public refs and
// view-local data. It never carries a widget, an object, or a host path,
// so history can be stored, restored, and deep-linked without leaking
// evidence truth or local filesystem structure.
import 'package:flutter/foundation.dart';

enum DestinationId {
  journey,
  plan,
  workflows,
  projects,
  swarms,
  roadmap,
  chat,
  compare,
  models,
  companion,
  code,
  eval,
  audit,
  lint,
  receipts,
  science,
  world,
  memory,
  governance,
  usage,
  studio,
  graph,
  feeds,
  discourse,
  academy,
  lessons,
  instruments,
  lanes,
  train,
  uplift,
  family,
  plugins,
}

@immutable
class AppLocation {
  final DestinationId routeId;

  /// Opaque public refs only: jrn_ on the journey destination, op_/rcpt_
  /// as a selection. Never a path, never candidate-controlled text.
  final String? journeyRef;
  final String? selectionRef;

  /// A short view-local token (the active lens, the open pane). Free-form
  /// but bounded public text.
  final String? viewState;
  final double scrollOffset;

  const AppLocation({
    required this.routeId,
    this.journeyRef,
    this.selectionRef,
    this.viewState,
    this.scrollOffset = 0,
  });

  AppLocation copyWith({double? scrollOffset}) => AppLocation(
        routeId: routeId,
        journeyRef: journeyRef,
        selectionRef: selectionRef,
        viewState: viewState,
        scrollOffset: scrollOffset ?? this.scrollOffset,
      );

  Map<String, Object?> toJson() => {
        'route': routeId.name,
        if (journeyRef != null) 'journey_ref': journeyRef,
        if (selectionRef != null) 'selection_ref': selectionRef,
        if (viewState != null) 'view_state': viewState,
        'scroll': scrollOffset,
      };

  static AppLocation? fromJson(Map<String, Object?> json) {
    final route = json['route'];
    if (route is! String) return null;
    final id = DestinationId.values.where((v) => v.name == route).toList();
    if (id.isEmpty) return null;
    final scroll = json['scroll'];
    return AppLocation(
      routeId: id.single,
      journeyRef: json['journey_ref'] is String
          ? json['journey_ref'] as String
          : null,
      selectionRef: json['selection_ref'] is String
          ? json['selection_ref'] as String
          : null,
      viewState:
          json['view_state'] is String ? json['view_state'] as String : null,
      scrollOffset: scroll is num ? scroll.toDouble() : 0,
    );
  }

  @override
  bool operator ==(Object other) =>
      other is AppLocation &&
      other.routeId == routeId &&
      other.journeyRef == journeyRef &&
      other.selectionRef == selectionRef &&
      other.viewState == viewState &&
      other.scrollOffset == scrollOffset;

  @override
  int get hashCode => Object.hash(
      routeId, journeyRef, selectionRef, viewState, scrollOffset);
}

final _jrnRef = RegExp(r'^jrn_[0-9a-f]{32}$');
final _selectionRef = RegExp(r'^(op|rcpt)_[0-9a-f]{32}$');

/// Parse a deep link of the form `flywheel://dest/<route>[?ref=<opaque>]`.
/// Anything else -- other schemes or hosts, extra path segments, unknown
/// query keys, non-opaque refs, a journey ref on a foreign destination --
/// is rejected with null, never guessed.
AppLocation? parseDeepLink(Uri uri) {
  if (uri.scheme != 'flywheel' || uri.host != 'dest') return null;
  final segments = uri.pathSegments;
  if (segments.length != 1) return null;
  final id = DestinationId.values.where((v) => v.name == segments.single);
  if (id.isEmpty) return null;
  final routeId = id.single;
  if (uri.queryParameters.keys.any((key) => key != 'ref')) {
    return null;
  }
  final ref = uri.queryParameters['ref'];
  if (ref == null) {
    return AppLocation(routeId: routeId);
  }
  if (routeId == DestinationId.journey) {
    return _jrnRef.hasMatch(ref)
        ? AppLocation(routeId: routeId, journeyRef: ref)
        : null;
  }
  if (routeId == DestinationId.receipts && _selectionRef.hasMatch(ref)) {
    return AppLocation(routeId: routeId, selectionRef: ref);
  }
  if ((routeId == DestinationId.plan ||
          routeId == DestinationId.studio ||
          routeId == DestinationId.graph) &&
      _selectionRef.hasMatch(ref)) {
    return AppLocation(routeId: routeId, selectionRef: ref);
  }
  return null;
}
