part of 'flywheel_shell.dart';

extension _FlywheelShellStatus on _FlywheelShellState {
  Widget _statusBar() => Column(mainAxisSize: MainAxisSize.min, children: [
        RowanActionCueStrip(captions: _rowanCues.controller.captions),
        Row(children: [
          Expanded(
            child: AnimatedBuilder(
              animation: _coordinator,
              builder: (context, _) => StatusBar(
                alive: _coordinator.alive,
                message: _coordinator.message,
                startError: _coordinator.startError,
                world: _coordinator.world,
                onStartEngine: () => unawaited(_coordinator.start()),
                local: !_mobile,
                gatewayAddress:
                    Uri.tryParse(_dependencies.client.baseUrl)?.authority ??
                        _dependencies.client.baseUrl,
              ),
            ),
          ),
          IconButton(
            tooltip: 'Rowan voice',
            icon: const Icon(Icons.record_voice_over_outlined, size: 20),
            onPressed: () => showModalBottomSheet<void>(
              context: context,
              isScrollControlled: true,
              builder: (_) => SafeArea(
                child: SingleChildScrollView(
                  child: RowanActionCueControls(
                    controller: _rowanCues.controller,
                    title: 'Rowan voice',
                  ),
                ),
              ),
            ),
          ),
        ]),
      ]);
}
