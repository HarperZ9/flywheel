// sessions_panel.dart -- your sessions, on any device.
//
// Lists the journeys the gateway holds (server-side and resumable) so a session
// started on the PC shows up on a phone pointed at the same gateway, and tapping
// one reopens it here. Read-only over the gateway list; opening delegates to the
// journey controller's resume-and-persist path.

import 'package:flutter/material.dart';

import '../client/journey_api.dart';
import '../models/journey_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

Future<void> showSessionsPanel(
  BuildContext context, {
  required JourneyApi api,
  required void Function(String ref, JourneyLens lens) onOpen,
}) {
  return showDialog(
    context: context,
    builder: (ctx) => Dialog(
      backgroundColor: ctx.fw.ground,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460, maxHeight: 560),
        child: Padding(
          padding: const EdgeInsets.all(FwLayout.s5),
          child: SessionsPanel(api: api, onOpen: onOpen),
        ),
      ),
    ),
  );
}

class SessionsPanel extends StatefulWidget {
  final JourneyApi api;
  final void Function(String ref, JourneyLens lens) onOpen;
  const SessionsPanel({super.key, required this.api, required this.onOpen});

  @override
  State<SessionsPanel> createState() => _SessionsPanelState();
}

class _SessionsPanelState extends State<SessionsPanel> {
  List<JourneySummary>? _sessions;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final list = await widget.api.list();
      if (!mounted) return;
      setState(() => _sessions = list);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '$e');
    }
  }

  void _open(JourneySummary s) {
    final lens = s.lens ?? JourneyLens.verify;
    Navigator.of(context).maybePop();
    widget.onOpen(s.journeyRef, lens);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Kicker('sessions', hot: true),
        const SizedBox(height: FwLayout.s2),
        const Text('Your sessions, on any device.',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        const SizedBox(height: FwLayout.s2),
        Text('The work the gateway is holding. Tap one to reopen it here.',
            style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        const SizedBox(height: FwLayout.s4),
        Flexible(child: _body(t)),
      ],
    );
  }

  Widget _body(FwTokens t) {
    if (_error != null) {
      return HonestNull('Could not reach the gateway to list sessions. $_error');
    }
    final sessions = _sessions;
    if (sessions == null) {
      return const Padding(
        padding: EdgeInsets.all(FwLayout.s4),
        child: Center(
          child: SizedBox(
              width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
        ),
      );
    }
    final real = sessions
        .where((s) => !s.invalidResponse && s.journeyRef.isNotEmpty)
        .toList();
    if (real.isEmpty) {
      return const HonestNull(
          'No sessions yet. Start one and it will follow you here.');
    }
    return ListView.separated(
      shrinkWrap: true,
      itemCount: real.length,
      separatorBuilder: (_, __) => const SizedBox(height: FwLayout.s2),
      itemBuilder: (context, i) => _row(t, real[i]),
    );
  }

  Widget _row(FwTokens t, JourneySummary s) {
    return HairlineCard(
      child: InkWell(
        onTap: () => _open(s),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(s.journeyRef,
                      style: fwMono(t, size: 11), overflow: TextOverflow.ellipsis),
                  const SizedBox(height: 2),
                  Text(
                      '${s.rawStage}${s.lens != null ? ' · ${s.lens!.name}' : ''}',
                      style: fwMono(t, size: 10, color: t.inkFaint)),
                ],
              ),
            ),
            Text('open', style: fwMono(t, size: 10, color: t.inkMuted)),
          ]),
        ),
      ),
    );
  }
}
