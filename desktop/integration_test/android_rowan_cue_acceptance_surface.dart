part of 'android_rowan_cue_acceptance_test.dart';

final class _HarnessMount {
  const _HarnessMount({
    required this.rowan,
    required this.host,
    required this.sharing,
    required this.cues,
    required this.operationKey,
  });

  final RowanOperationController rowan;
  final RowanOperationHostAdapter host;
  final LiveScreenSharing sharing;
  final ShellRowanCues cues;
  final GlobalKey operationKey;

  BuildContext get context {
    final value = operationKey.currentContext;
    if (value == null) throw StateError('operation context is not mounted');
    return value;
  }

  Future<void> dispose() async {
    await cues.dispose();
    sharing.dispose();
    host.dispose();
    rowan.dispose();
  }
}

final class _RowanCueAcceptanceSurface extends StatelessWidget {
  const _RowanCueAcceptanceSurface({super.key, required this.cues});

  final ShellRowanCues cues;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(
          child: Column(
            children: [
              RowanActionCueStrip(captions: cues.controller.captions),
              Align(
                alignment: Alignment.centerRight,
                child: IconButton(
                  tooltip: 'Rowan voice',
                  icon: const Icon(Icons.record_voice_over_outlined),
                  onPressed: () => showModalBottomSheet<void>(
                    context: context,
                    isScrollControlled: true,
                    builder: (_) => SafeArea(
                      child: SingleChildScrollView(
                        child: RowanActionCueControls(
                          controller: cues.controller,
                          title: 'Rowan voice',
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const Expanded(
                child: Center(
                  child: Text('Rowan Android cue acceptance'),
                ),
              ),
            ],
          ),
        ),
      );
}
