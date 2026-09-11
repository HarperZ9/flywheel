import 'package:flutter/material.dart';
import '../client/agent_trace_reader.dart';
import '../controllers/agent_caption_controller.dart';
import '../models/agent_trace.dart';
import '../theme/flywheel_theme.dart';
import 'agent_caption_row.dart';
import 'fw.dart';

/// Private, opt-in captions. The host supplies accepted operation metadata.
class AgentCaptionPanel extends StatefulWidget {
  final AgentTraceReader reader;
  final TraceProjection projection;
  final VoidCallback? onClose;
  const AgentCaptionPanel(
      {super.key,
      required this.reader,
      required this.projection,
      this.onClose});
  @override
  State<AgentCaptionPanel> createState() => _AgentCaptionPanelState();
}

class _AgentCaptionPanelState extends State<AgentCaptionPanel> {
  late AgentCaptionController _state;
  final _scroll = ScrollController();
  double _size = 18;
  int? _original;
  @override
  void initState() {
    super.initState();
    _create();
  }

  void _create() {
    _state = AgentCaptionController(
        reader: widget.reader, projection: widget.projection)
      ..addListener(_changed);
  }

  void _release() {
    _state.removeListener(_changed);
    _state.dispose();
  }

  void _changed() {
    if (!mounted) return;
    setState(() {});
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          !_state.following ||
          !_state.active ||
          !_scroll.hasClients) {
        return;
      }
      final media = MediaQuery.of(context);
      if (media.disableAnimations || media.accessibleNavigation) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      } else {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 150), curve: Curves.easeOut);
      }
    });
  }

  @override
  void didUpdateWidget(covariant AgentCaptionPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    final old = oldWidget.projection, next = widget.projection;
    if (oldWidget.reader != widget.reader ||
        old.operationRef != next.operationRef ||
        old.journeyRef != next.journeyRef ||
        old.traceRef != next.traceRef) {
      _release();
      _original = null;
      _create();
    } else if (old.projectionSha256 != next.projectionSha256) {
      _state.updateProjection(next);
    }
  }

  @override
  void dispose() {
    _release();
    _scroll.dispose();
    super.dispose();
  }

  void _close() {
    _original = null;
    _state.close();
    widget.onClose?.call();
  }

  @override
  Widget build(BuildContext context) {
    final captions = _state.captions;
    return HairlineCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('Private captions'),
      const Text(
          'Provider summary unavailable: this trace has no supported summary channel. '
          'Hidden provider reasoning is unavailable. Recorded inference lifecycle '
          'events are shown when present.'),
      Text(
          'Original assistant output, tool activity and reported progress. '
          'Receipt time is local; event time is unavailable. Hashes establish bytes and bindings, not truth.',
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(color: context.fw.inkMuted)),
      if (!_state.active)
        TextButton(
            onPressed: _state.failure == null ? _state.start : null,
            child: const Text('Start private captions')),
      if (_state.active) ...[
        Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
          TextButton(
              onPressed: () => _state.setFollowing(!_state.following),
              child: Text(_state.following ? 'Pause follow' : 'Resume follow')),
          IconButton(
              tooltip: 'Smaller captions',
              constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
              onPressed: _size > 14 ? () => setState(() => _size -= 2) : null,
              icon: const Icon(Icons.text_decrease)),
          IconButton(
              tooltip: 'Larger captions',
              constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
              onPressed: _size < 28 ? () => setState(() => _size += 2) : null,
              icon: const Icon(Icons.text_increase)),
          TextButton(onPressed: _close, child: const Text('Close captions')),
        ]),
        Text(
            '${_state.readCount} records received · ${_state.uncaptionedRecords} without a caption mapping'),
        Text(_state.caughtUp
            ? 'Read matches the advertised ${widget.projection.isRunning ? 'prefix' : 'trace'} head.'
            : 'Partial read: the advertised head is not checked yet.'),
        if (widget.projection.isPartialExecution)
          const Text(
              'Partial execution: only the retained prefix is available.'),
        if (_state.reading) const Text('Reading private records…'),
        if (_state.caughtUp && widget.projection.isRunning)
          const Text('Waiting for accepted trace metadata.'),
        if (captions.isNotEmpty)
          SizedBox(
              height: 320,
              child: NotificationListener<ScrollStartNotification>(
                  onNotification: (event) {
                    if (event.dragDetails != null) _state.setFollowing(false);
                    return false;
                  },
                  child: ListView.builder(
                      controller: _scroll,
                      itemCount: captions.length,
                      itemBuilder: (context, index) => AgentCaptionRow(
                          caption: captions[index],
                          size: _size,
                          showOriginal: _original == index,
                          onToggleOriginal: () {
                            _state.setFollowing(false);
                            setState(() =>
                                _original = _original == index ? null : index);
                          })))),
      ],
      if (_state.failure != null) ...[
        Text('Private captions unavailable (${_state.failure!.name}). '
            'Any displayed prefix is partial; no action was resubmitted.'),
        if (_state.active)
          TextButton(
              onPressed: _state.reading ? null : _state.retry,
              child: const Text('Retry private read')),
      ],
    ]));
  }
}
