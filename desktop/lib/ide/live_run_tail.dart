// live_run_tail.dart — the live agent run's event stream, and the loop's
// terminal action: when the done event says files were edited, the same
// sign-this-run attestation offered on stored runs is offered here, so a
// reviewer never has to leave the live surface to take ownership.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/agent_timeline.dart';
import '../widgets/sign_run_panel.dart';

class LiveRunTail extends StatelessWidget {
  final List<Map<String, dynamic>> events;
  final ScrollController scroll;
  final GatewayClient client;
  const LiveRunTail(
      {super.key,
      required this.events,
      required this.scroll,
      required this.client});

  Map<String, dynamic>? get _done {
    for (final e in events.reversed) {
      if (e['type'] == 'done') return e;
    }
    return null;
  }

  bool get _editedFiles {
    final review = _done?['review'];
    if (review is! Map<String, dynamic>) return false;
    final files = review['files_edited'];
    return files is List && files.isNotEmpty;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 240),
        child: SingleChildScrollView(
          controller: scroll,
          child: AgentTimeline(events: events),
        ),
      ),
      if (_editedFiles)
        TextButton.icon(
          onPressed: () => showModalBottomSheet(
            context: context,
            isScrollControlled: true,
            backgroundColor: t.ground,
            builder: (ctx) => Padding(
              padding: const EdgeInsets.all(FwLayout.s4),
              child: SingleChildScrollView(
                  child: SignRunPanel(client: client, run: _done!)),
            ),
          ),
          icon: const Icon(Icons.draw_outlined, size: 14),
          label: const Text('sign this run'),
        ),
    ]);
  }
}
