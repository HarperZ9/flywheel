import 'dart:async';

import 'package:flutter/material.dart';

import '../controllers/live_screen_sharing.dart';
import '../controllers/rowan_walkthrough_operation_host.dart';
import 'live_screen_panel.dart';
import 'operation_grant_sheet.dart';

/// Both surfaces share the shell-owned handle and the same approval pathway.
class ScreenSharingSurface extends StatefulWidget {
  const ScreenSharingSurface(
      {super.key,
      required this.sharing,
      this.modelHost,
      this.compact = false,
      this.onOpenStudio});
  final LiveScreenSharing sharing;
  final RowanWalkthroughOperationHost? modelHost;
  final bool compact;
  final VoidCallback? onOpenStudio;
  @override
  State<ScreenSharingSurface> createState() => _ScreenSharingSurfaceState();
}

class _ScreenSharingSurfaceState extends State<ScreenSharingSurface> {
  @override
  void initState() {
    super.initState();
    if (!widget.compact) unawaited(widget.sharing.refreshSources());
  }

  ScreenAuthorizer get _authorize => (operation, current, dispatch) =>
      authorizeGatewayOperationDetailed(context, operation, dispatch,
          currentOperation: current);

  VoidCallback? _control(String action) =>
      widget.sharing.busy || !widget.sharing.hasSession
          ? null
          : () => unawaited(widget.sharing.control(action, _authorize));

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: Listenable.merge([widget.sharing, widget.modelHost]),
      builder: (context, _) {
        final sharing = widget.sharing, feed = sharing.feed;
        if (widget.compact) {
          if (!sharing.hasUnresolvedCapture && !sharing.busy) {
            return const SizedBox.shrink();
          }
          final state = switch (feed.state) {
            ScreenCaptureState.running => 'Screen sharing active',
            ScreenCaptureState.paused => 'Screen sharing paused',
            ScreenCaptureState.disconnected =>
              'Screen connection lost; capture may continue',
            _ => 'Screen sharing pending',
          };
          return Material(
              child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            child: Wrap(
                spacing: 12,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Semantics(liveRegion: true, child: Text(state)),
                  if (sharing.uncertainOpen)
                    OutlinedButton(
                        onPressed: sharing.busy
                            ? null
                            : () => unawaited(sharing.recover()),
                        child: const Text('Recover share')),
                  if (feed.state == ScreenCaptureState.running)
                    OutlinedButton(
                        onPressed: _control('pause'),
                        child: const Text('Pause')),
                  if (feed.state == ScreenCaptureState.paused)
                    OutlinedButton(
                        onPressed: _control('resume'),
                        child: const Text('Resume')),
                  if (sharing.hasSession)
                    OutlinedButton(
                        onPressed: _control('stop'),
                        child: const Text('Stop sharing')),
                  TextButton(
                      onPressed: widget.onOpenStudio,
                      child: const Text('Open screen feed')),
                  if (sharing.error != null) Text(sharing.error!),
                ]),
          ));
        }
        final host = widget.modelHost;
        return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(sharing.hasSession
                  ? 'Bound model: ${sharing.boundModel} · ${sharing.boundDestination}'
                  : 'Selected model: ${host?.selectedModel ?? "Select a model in Rowan"}'),
              const SizedBox(height: 8),
              const Text(
                  'Share selected monitors for up to two minutes per approval. '
                  'Model delivery uses sampled images and requires its own authorized operation.'),
              const SizedBox(height: 8),
              Wrap(spacing: 8, children: [
                if (sharing.uncertainOpen)
                  OutlinedButton(
                      onPressed: sharing.busy
                          ? null
                          : () => unawaited(sharing.recover()),
                      child: const Text('Recover share')),
                TextButton(
                    onPressed: sharing.loading || sharing.busy
                        ? null
                        : () => unawaited(sharing.refreshSources()),
                    child: Text(sharing.loading
                        ? 'Reading sources…'
                        : 'Refresh sources')),
                if (sharing.hasSession &&
                    feed.state == ScreenCaptureState.disconnected)
                  TextButton(
                      onPressed: sharing.busy
                          ? null
                          : () => unawaited(sharing.reconnect()),
                      child: const Text('Reconnect feed')),
              ]),
              LiveScreenPanel(
                sources: sharing.sources,
                selected: sharing.selected,
                state: sharing.uncertainOpen
                    ? ScreenCaptureState.disconnected
                    : sharing.busy && !sharing.hasSession
                        ? ScreenCaptureState.starting
                        : feed.state,
                hasSession: sharing.hasUnresolvedCapture,
                onSelectionChanged: sharing.select,
                onStart:
                    sharing.busy || sharing.hasUnresolvedCapture || host == null
                        ? null
                        : () => unawaited(sharing.start(_authorize,
                            destination: () => host.endpoint,
                            model: () => host.selectedModel)),
                onPause: _control('pause'),
                onResume: _control('resume'),
                onStop: _control('stop'),
                previewSourceId: feed.viewedSource,
                onPreviewSourceChanged: feed.viewSource,
                previewBytes: feed.previewBytes,
                previewFrame: feed.previewFrame,
                delivery: feed.delivery,
                deliveredFrame: feed.deliveredFrame,
                error: sharing.error ?? feed.error,
              ),
            ]);
      });
}
