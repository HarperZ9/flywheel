part of 'flywheel_shell.dart';

extension _FlywheelShellActiveView on _FlywheelShellState {
  Widget _activeView() {
    final location = _navigation.current;
    final acceptsArgument = _acceptsArgument(location.routeId);
    final argument = acceptsArgument ? _pendingArgument : null;
    if (acceptsArgument) _pendingArgument = null;
    return AnimatedBuilder(
      animation: Listenable.merge([_coordinator, _navigation]),
      builder: (context, _) => _views.viewFor(location, (_) {
        return buildDestinationView(
          location.routeId,
          DestinationInputs(
            client: _dependencies.client,
            journey: _dependencies.journey,
            rowanOperationHost: _dependencies.rowanOperationHost,
            screenSharing: _screenSharing,
            actionCueController: _rowanCues.controller,
            code: _dependencies.code,
            codeGuard: _guard,
            alive: _coordinator.alive,
            settings: widget.settings,
            chatStore: _dependencies.chatStore,
            chatDraftStore: _dependencies.chatDraftStore,
            pendingArgument: argument,
            roster: _coordinator.roster,
            world: _coordinator.world,
            onProbe: () => unawaited(_coordinator.probeLanes()),
            onInstall: (name) async => await _coordinator.installLane(name),
            onStartEngine: () => unawaited(_coordinator.start()),
          ),
        );
      }),
    );
  }
}
