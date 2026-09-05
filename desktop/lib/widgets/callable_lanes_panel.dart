// callable_lanes_panel.dart - the callable surface of the lane layer.
//
// The roster above it answers "what is installed". This answers "what may I
// call, and what does it demand", which the app had no way to show: the route
// existed and nothing reached it.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/callable_lane.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class CallableLanesPanel extends StatefulWidget {
  final GatewayClient client;

  /// When the engine is not reachable the panel says so rather than showing
  /// an empty list, which would read as "no lanes are callable".
  final bool alive;

  const CallableLanesPanel(
      {super.key, required this.client, required this.alive});

  @override
  State<CallableLanesPanel> createState() => _CallableLanesPanelState();
}

class _CallableLanesPanelState extends State<CallableLanesPanel> {
  List<CallableLane>? _lanes;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    if (widget.alive) _load();
  }

  @override
  void didUpdateWidget(CallableLanesPanel old) {
    super.didUpdateWidget(old);
    if (widget.alive && !old.alive) _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final json = await widget.client.callableLanes();
      if (!mounted) return;
      setState(() {
        _lanes = CallableLane.listFrom(json);
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (!widget.alive) {
      return const HonestNull(
          'The engine is offline, so what is callable is unknown.');
    }
    if (_loading) return const LinearProgressIndicator(minHeight: 2);
    if (_error != null) {
      return HonestNull('The callable lane list could not be read: $_error');
    }
    final lanes = _lanes;
    if (lanes == null) return const SizedBox.shrink();
    if (lanes.isEmpty) {
      return const HonestNull('No lane reports itself as callable.');
    }
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('callable'),
          const SizedBox(height: FwLayout.s1),
          Text('${lanes.length} lanes can be called. The tier is what a call '
              'demands before it runs. A lane printing two charges more for '
              'the tools that change something.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: t.inkMuted)),
          const SizedBox(height: FwLayout.s2),
          for (final lane in lanes)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 92,
                    child: Text(lane.name,
                        style: fwMono(t, size: 11.5, color: t.ink)),
                  ),
                  SizedBox(
                    width: 46,
                    child: Text(lane.tierLabel,
                        style: fwMono(t, size: 11, color: t.inkMuted)),
                  ),
                  SizedBox(
                    width: 96,
                    child: Text(lane.organ,
                        style: fwMono(t, size: 11, color: t.inkFaint)),
                  ),
                  Expanded(
                    child: Text(lane.description,
                        style: Theme.of(context)
                            .textTheme
                            .bodySmall
                            ?.copyWith(color: t.inkMuted)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
