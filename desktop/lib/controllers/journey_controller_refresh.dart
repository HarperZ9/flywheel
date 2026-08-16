part of 'journey_controller.dart';

extension JourneyControllerRefresh on JourneyController {
  Future<void> selectJourney(String ref) => _select(ref, _view.lens, false);

  Future<void> selectLens(JourneyLens lens) =>
      _view.projection == null || lens == JourneyLens.invalidResponse
          ? Future.sync(() => _view.remote(_invalid()))
          : _select(_view.ref!, lens, true);

  Future<void> refreshActiveProjection() {
    final ref = _view.ref;
    return ref == null ? Future.value() : _select(ref, _view.lens, false);
  }
}
