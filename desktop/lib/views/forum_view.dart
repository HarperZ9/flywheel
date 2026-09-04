// forum_view.dart - the orchestration lane: its run room, its ledger, and
// the waves paused for a human.
//
// Four gateway reads that had no native surface at all. The lane speaks for
// itself here: its brief is rendered as written and the client composes no
// summary of its own, because a second summary is a second claim.
//
// An intact ledger chain is not answer acceptance. The view says that in
// words rather than letting a verified tick imply something it does not mean.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../client/gateway_forum.dart';
import '../models/forum_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class ForumView extends StatefulWidget {
  final GatewayClient client;
  const ForumView({super.key, required this.client});

  @override
  State<ForumView> createState() => _ForumViewState();
}

class _ForumViewState extends State<ForumView> {
  ForumStatus? _status;
  ForumLedger? _ledger;
  ForumGates? _gates;
  ForumRunRoom? _room;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      // Four independent reads: one round trip each, awaited together so a
      // slow lane costs one timeout rather than four.
      final results = await Future.wait([
        widget.client.forumStatus(),
        widget.client.forumLedger(),
        widget.client.forumGates(),
        widget.client.forumRunRoom(),
      ]);
      if (!mounted) return;
      setState(() {
        _status = ForumStatus.fromJson(results[0]);
        _ledger = ForumLedger.fromJson(results[1]);
        _gates = ForumGates.fromJson(results[2]);
        _room = ForumRunRoom.fromJson(results[3]);
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
    return ViewScroll(
      children: [
        SectionHeader(
          'Forum',
          kicker: 'witnessed causal ledger, model-agnostic routing',
          trailing: IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh, size: 18),
            onPressed: _loading ? null : _load,
          ),
        ),
        if (_loading) ...[
          const SizedBox(height: FwLayout.s2),
          const LinearProgressIndicator(minHeight: 2),
        ],
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull('The forum lane could not be read: $_error'),
        ],
        if (_room != null) ...[
          const SizedBox(height: FwLayout.s3),
          _runRoom(t, _room!),
        ],
        if (_gates != null) ...[
          const SizedBox(height: FwLayout.s3),
          _gatesCard(t, _gates!),
        ],
        if (_ledger != null) ...[
          const SizedBox(height: FwLayout.s3),
          _ledgerCard(t, _ledger!),
        ],
        if (_status != null) ...[
          const SizedBox(height: FwLayout.s3),
          _statusCard(t, _status!),
        ],
      ],
    );
  }

  Widget _runRoom(FwTokens t, ForumRunRoom room) {
    if (room.offline != null) {
      return HonestNull('Run room unavailable: ${room.offline!.reason}');
    }
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('run room'),
          const SizedBox(height: FwLayout.s1),
          Text(room.title,
              style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: FwLayout.s1),
          Text(room.summary,
              style: Theme.of(context).textTheme.bodyMedium),
          if (room.risk.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s1),
            Text(room.risk,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: t.inkMuted)),
          ],
          if (room.nextStep.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s1),
            Text('Next: ${room.nextStep}',
                style: fwMono(t, size: 11.5, color: t.inkSoft)),
          ],
          if (room.bullets.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            for (final b in room.bullets)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child:
                    Text('- $b', style: fwMono(t, size: 11, color: t.inkMuted)),
              ),
          ],
        ],
      ),
    );
  }

  Widget _gatesCard(FwTokens t, ForumGates gates) {
    if (gates.offline != null) {
      return HonestNull('Gates unavailable: ${gates.offline!.reason}');
    }
    if (gates.pending.isEmpty) {
      return const HonestNull('No wave is waiting for approval.');
    }
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('waiting for a human'),
          const SizedBox(height: FwLayout.s1),
          for (final g in gates.pending)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text('run ${g.runSeq} wave ${g.wave}  ${g.label}',
                  style: fwMono(t, size: 11.5, color: t.ink)),
            ),
        ],
      ),
    );
  }

  Widget _ledgerCard(FwTokens t, ForumLedger l) {
    if (l.offline != null) {
      return HonestNull('Ledger unavailable: ${l.offline!.reason}');
    }
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('ledger'),
          const SizedBox(height: FwLayout.s2),
          AdaptiveTiles(children: [
            StatTile(label: 'entries', value: '${l.entries}'),
            StatTile(label: 'requests', value: '${l.requests}'),
            StatTile(label: 'tasks', value: '${l.tasks}'),
            StatTile(label: 'answers', value: '${l.answers}'),
            StatTile(label: 'escalations', value: '${l.escalations}'),
            StatTile(label: 'budget stops', value: '${l.budgetStops}'),
          ]),
          const SizedBox(height: FwLayout.s2),
          if (l.isEmpty)
            const HonestNull('The ledger is empty. No run has been witnessed.')
          else
            HashText('checkpoint', l.checkpoint),
          const SizedBox(height: FwLayout.s1),
          // The distinction the tick must not blur.
          Text(
            l.verified
                ? 'Chain verified. An intact chain is not answer acceptance.'
                : 'Chain NOT verified.',
            style: fwMono(t,
                size: 11,
                color: l.verified ? t.verified : t.drift),
          ),
        ],
      ),
    );
  }

  Widget _statusCard(FwTokens t, ForumStatus s) {
    if (s.offline != null) {
      return HonestNull('Lane offline: ${s.offline!.reason}');
    }
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('lane'),
          const SizedBox(height: FwLayout.s1),
          Text('forum ${s.version}  ${s.role}',
              style: fwMono(t, size: 11.5, color: t.ink)),
          if (s.currentStatus.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s1),
            Text(s.currentStatus,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: t.inkMuted)),
          ],
        ],
      ),
    );
  }
}
