part of 'rowan_walkthrough_panel.dart';

typedef RowanWalkthroughCaptionBuilder = Widget Function(
  BuildContext context,
  RowanWalkthroughController controller,
);
typedef RowanWalkthroughFollowUpReviewer = Future<void> Function(
  OperationSnapshot snapshot,
  OperationResult result,
);

class _RowanWalkthroughSelectors extends StatelessWidget {
  final GatewayClient client;
  final RowanWalkthroughController controller;
  final List<EndpointRow> endpoints;
  final GatewayJourneyBinding? binding;
  final bool alive;
  final TextEditingController root;

  const _RowanWalkthroughSelectors({
    required this.client,
    required this.controller,
    required this.endpoints,
    required this.binding,
    required this.alive,
    required this.root,
  });

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: FwLayout.s3,
        runSpacing: FwLayout.s3,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          DropdownButton<String>(
            value: controller.endpoint,
            hint: const Text('endpoint'),
            items: [
              for (final endpoint in endpoints)
                DropdownMenuItem(
                  value: endpoint.name,
                  child: Text(endpoint.name),
                ),
            ],
            onChanged: controller.selectEndpoint,
          ),
          ModelSelectorButton(
            loadModels: () => client.models(controller.endpoint ?? ''),
            current: controller.selectedModel,
            onSelect: controller.selectModel,
            enabled: alive && controller.endpoint != null,
          ),
          SizedBox(
            width: 260,
            child: TextField(
              key: const Key('rowan-walkthrough-root'),
              controller: root,
              enabled: alive,
              decoration: const InputDecoration(labelText: 'Input repo root'),
              onChanged: controller.setRoot,
            ),
          ),
          Text(
            binding == null
                ? 'Journey not selected'
                : 'Journey ${binding!.journeyRef} @ '
                    '${binding!.eventHead.substring(0, 12)}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      );
}

class _RowanWalkthroughChips extends StatelessWidget {
  final RowanWalkthroughController controller;
  const _RowanWalkthroughChips({required this.controller});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
      _chip(t, 'scenario', controller.scenario.version),
      _chip(t, 'checkpoint', controller.checkpoint.name),
      _chip(t, 'oracle', controller.oracle.state.name),
      _chip(t, 'model', controller.selectedModel ?? 'select model'),
    ]);
  }

  Widget _chip(FwTokens t, String label, String value) => Container(
        padding:
            const EdgeInsets.symmetric(horizontal: FwLayout.s2, vertical: 6),
        decoration: BoxDecoration(
          border: Border.all(color: t.line),
          borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        ),
        child: Text('$label · $value', style: fwMono(t, size: 11.5)),
      );
}

class _RowanGuidanceControl extends StatelessWidget {
  final bool paused;
  final VoidCallback onToggle;
  const _RowanGuidanceControl({required this.paused, required this.onToggle});

  @override
  Widget build(BuildContext context) => Wrap(spacing: FwLayout.s2, children: [
        OutlinedButton(
          onPressed: onToggle,
          child: Text(paused ? 'Resume guidance' : 'Pause guidance'),
        ),
        const HonestNull('Guidance pause does not stop execution. Use Stop for '
            'an approved operation cancel.'),
      ]);
}

class _RowanCaptionSlot extends StatelessWidget {
  final RowanWalkthroughCaptionBuilder? builder;
  final RowanWalkthroughController controller;
  const _RowanCaptionSlot({required this.builder, required this.controller});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const HonestNull('Provider-visible reasoning captions attach here. '
              'Hidden internal chain-of-thought is unavailable and is never '
              'fabricated or exported by this panel.'),
          if (builder != null) ...[
            const SizedBox(height: FwLayout.s2),
            builder!(context, controller),
          ],
        ],
      );
}

class _RowanTerminalActions extends StatelessWidget {
  final RowanWalkthroughController controller;
  final bool followUpAvailable;
  final VoidCallback onReopen;
  final VoidCallback onReviewFollowUp;

  const _RowanTerminalActions({
    required this.controller,
    required this.followUpAvailable,
    required this.onReopen,
    required this.onReviewFollowUp,
  });

  @override
  Widget build(BuildContext context) {
    if (controller.checkpoint == RowanWalkthroughCheckpoint.semanticOracle) {
      return Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        HonestNull(controller.oracle.message),
        OutlinedButton(
          onPressed: onReopen,
          child: const Text('Reopen operation'),
        ),
      ]);
    }
    if (controller.canPrepareFollowUp) {
      return Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        const HonestNull(
            'The same operation record reopened; bounded follow-up '
            'can now be reviewed through an attached continuation provider.'),
        if (!followUpAvailable)
          const HonestNull('Follow-up review provider unavailable.')
        else
          OutlinedButton(
            onPressed: onReviewFollowUp,
            child: const Text('Review bounded follow-up'),
          ),
      ]);
    }
    if (controller.outcome != null) {
      return HonestNull('Walkthrough outcome: ${controller.outcome!.name}.');
    }
    return const SizedBox.shrink();
  }
}
