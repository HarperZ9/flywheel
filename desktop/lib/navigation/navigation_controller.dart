// navigation_controller.dart -- typed history over stable locations.
//
// go() waits for the unsaved-work guard before committing anything, back
// and forward restore the full location (journey ref, selection, view
// state, scroll), and history stores data only: no widgets, no objects,
// no host paths.
import 'package:flutter/foundation.dart';

import 'app_route.dart';
import 'destination_catalog.dart';

class NavigationController extends ChangeNotifier {
  // initial sets where the app opens. Desktop lands on Journey; a phone lands
  // on Chat, the surface a personal agent opens to. An unknown route falls
  // back to Journey rather than opening on nothing.
  NavigationController({
    required Future<bool> Function(String label) guard,
    AppLocation? initial,
  })  : _guard = guard,
        _current = initial != null && specFor(initial.routeId) != null
            ? initial
            : const AppLocation(routeId: DestinationId.journey);

  final Future<bool> Function(String label) _guard;

  AppLocation _current;
  final List<AppLocation> _back = [];
  final List<AppLocation> _forward = [];

  AppLocation get current => _current;
  bool get canBack => _back.isNotEmpty;
  bool get canForward => _forward.isNotEmpty;

  Future<bool> go(AppLocation next) async {
    if (next == _current) return true;
    final spec = specFor(next.routeId);
    if (spec == null) return false;
    if (!await _guard(spec.label)) return false;
    _back.add(_current);
    _forward.clear();
    _current = next;
    notifyListeners();
    return true;
  }

  Future<bool> back() async {
    if (_back.isEmpty) return false;
    final spec = specFor(_back.last.routeId);
    if (spec == null) return false;
    if (!await _guard(spec.label)) return false;
    final previous = _back.removeLast();
    _forward.add(_current);
    _current = previous;
    notifyListeners();
    return true;
  }

  Future<bool> forward() async {
    if (_forward.isEmpty) return false;
    final spec = specFor(_forward.last.routeId);
    if (spec == null) return false;
    if (!await _guard(spec.label)) return false;
    final next = _forward.removeLast();
    _back.add(_current);
    _current = next;
    notifyListeners();
    return true;
  }
}
