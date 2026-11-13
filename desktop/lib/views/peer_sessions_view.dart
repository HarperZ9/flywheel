// peer_sessions_view.dart — the peer sessions this machine can see on disk:
// Claude Code and Codex transcripts observed in bounded windows, the journey
// facts those windows support, and the file mailbox the peers write to. The
// observer never drives a session and never carries a transcript's text, so
// this surface shows counts, digests and receipts. Freshness is not liveness,
// and the wording beside every number says so.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

/// Shorten a digest for display. The whole value stays in the response; what
/// a reader compares by eye is the head, so only the head is rendered.
String _short(Object? value, [int chars = 12]) {
  final text = '$value';
  if (value == null || text.isEmpty) return 'none';
  return text.length <= chars ? text : text.substring(0, chars);
}

/// Render a file age without claiming it means the session is running. A
/// negative age is a clock disagreement between the writer and this host,
/// which is reported rather than clamped to zero.
String _age(Object? seconds) {
  if (seconds is! num) return 'unknown';
  if (seconds < 0) return 'written ahead of this clock';
  if (seconds < 90) return '${seconds.round()}s since last write';
  if (seconds < 5400) return '${(seconds / 60).round()}m since last write';
  return '${(seconds / 3600).round()}h since last write';
}

class PeerSessionsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const PeerSessionsView({
    super.key,
    required this.client,
    required this.alive,
  });

  @override
  State<PeerSessionsView> createState() => _PeerSessionsViewState();
}

class _PeerSessionsViewState extends State<PeerSessionsView> {
  Map<String, dynamic>? _registry;
  Map<String, dynamic>? _journey;
  Map<String, dynamic>? _mailbox;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(PeerSessionsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    try {
      final results = await Future.wait([
        widget.client.getJson('/api/peer-sessions'),
        widget.client.getJson('/api/peer-sessions/journey'),
        widget.client.getJson('/api/peer-sessions/mailbox'),
      ]);
      if (!mounted) return;
      setState(() {
        _registry = results[0];
        _journey = results[1];
        _mailbox = results[2];
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  /// The registry record differs per harness; the journey's facts are the one
  /// shape both harnesses project into, so the session list reads from there.
  List<Map<String, dynamic>> get _facts {
    final out = <Map<String, dynamic>>[];
    for (final event in (_journey?['events'] ?? const []) as List) {
      if (event is! Map) continue;
      final payload = event['payload'];
      if (payload is! Map) continue;
      for (final fact in (payload['facts'] ?? const []) as List) {
        if (fact is Map) out.add(fact.cast<String, dynamic>());
      }
    }
    return out;
  }

  List<Map<String, dynamic>> get _messages {
    final rows = (_mailbox?['messages'] ?? const []) as List;
    return [
      for (final row in rows)
        if (row is Map) row.cast<String, dynamic>(),
    ];
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
        'The engine is offline. Peer sessions appear when it runs.',
        command: 'flywheel up',
      );
    }
    final t = context.fw;
    final r = _registry;
    return ViewScroll(
      storageKey: 'peers',
      children: [
        SectionHeader(
          'Peers',
          kicker: 'transcripts read, never sessions driven',
          trailing:
              OutlinedButton(onPressed: _load, child: const Text('Refresh')),
        ),
        const SizedBox(height: FwLayout.s3),
        if (_error != null) HonestNull('Failed: $_error'),
        if (r != null) ..._registrySection(t, r),
        if (r != null) ..._sessionSection(t),
        ..._mailboxSection(t),
        const SizedBox(height: FwLayout.s4),
        if (r != null) HonestNull('${r['does_not_prove']}'),
      ],
    );
  }

  List<Widget> _registrySection(FwTokens t, Map<String, dynamic> r) {
    final failures = r['observe_failures'];
    final failed = failures is num && failures > 0;
    return [
      AdaptiveTiles(children: [
        StatTile(label: 'transcripts found', value: '${r['discovered']}'),
        StatTile(
          label: 'windows read',
          value: '${r['observed_count']} of ${r['discovered']}',
        ),
        StatTile(
          label: 'read failures',
          value: '$failures',
          status: failed ? 'drift' : null,
        ),
      ]),
      const SizedBox(height: FwLayout.s3),
      HairlineCard(
        recessed: true,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('registry ${_short(r['registry_sha256'], 16)}',
                style: fwMono(t, size: 11.5)),
            const SizedBox(height: FwLayout.s1),
            Text(
              'read at ${r['observed_at']} · ${r['unobserved_count']} left '
              'unread at this limit',
              style: fwMono(t, size: 11, color: t.inkFaint),
            ),
          ],
        ),
      ),
    ];
  }

  List<Widget> _sessionSection(FwTokens t) {
    final facts = _facts;
    return [
      const SizedBox(height: FwLayout.s4),
      const Kicker('sessions on this machine', hot: true),
      const SizedBox(height: FwLayout.s2),
      if (facts.isEmpty)
        const HonestNull('No transcript was read. Nothing is claimed about '
            'whether a peer session exists.'),
      for (final fact in facts) ...[
        _factCard(t, fact),
        const SizedBox(height: FwLayout.s2),
      ],
    ];
  }

  Widget _factCard(FwTokens t, Map<String, dynamic> fact) {
    final issues = (fact['issues'] ?? const []) as List;
    final refs = (fact['receipt_refs'] ?? const []) as List;
    final ref = fact['session_ref'];
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text('${fact['harness']}',
                  style: fwMono(t, size: 12.5, color: t.ink)),
            ),
            Text(
              ref == null ? 'id not id-shaped' : _short(ref, 13),
              style: fwMono(t, size: 11.5, color: t.inkMuted),
            ),
          ]),
          const SizedBox(height: FwLayout.s2),
          Text('${fact['statement']}',
              style: fwMono(t, size: 11.5, color: t.inkSoft)),
          const SizedBox(height: FwLayout.s2),
          Text(
            '${_age(fact['file_age_seconds'])} · class ${fact['activity']} · '
            'window ${_short(refs.isEmpty ? null : refs.first, 18)}',
            style: fwMono(t, size: 11, color: t.inkFaint),
          ),
          if (issues.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Wrap(
              spacing: FwLayout.s1,
              runSpacing: FwLayout.s1,
              children: [
                for (final issue in issues)
                  VerdictPill('$issue', status: 'drift'),
              ],
            ),
          ],
        ],
      ),
    );
  }

  List<Widget> _mailboxSection(FwTokens t) {
    final box = _mailbox;
    if (box == null) return const [];
    final present = box['mailbox_present'] == true;
    final rows = _messages;
    return [
      const SizedBox(height: FwLayout.s4),
      const Kicker('peer mailbox · header and receipt only'),
      const SizedBox(height: FwLayout.s2),
      if (!present)
        const HonestNull('No mailbox directory exists yet. That is the state '
            'before a peer writes its first message.')
      else if (rows.isEmpty)
        const HonestNull('The mailbox exists and holds no named message.')
      else
        HairlineCard(
          child: Column(children: [
            for (final row in rows) ...[
              _messageRow(t, row),
              if (row != rows.last) const SizedBox(height: FwLayout.s3),
            ],
          ]),
        ),
    ];
  }

  Widget _messageRow(FwTokens t, Map<String, dynamic> row) {
    final state = '${row['receipt_state']}'.toLowerCase();
    final renamed = row['file_name_consistent'] == false;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          Expanded(
            child: Text('${row['from']} to ${row['to']}',
                style: fwMono(t, size: 12, color: t.ink)),
          ),
          VerdictPill('${row['receipt_state']}',
              status: state == 'match' ? 'match' : 'drift'),
        ]),
        const SizedBox(height: FwLayout.s1),
        Text(
          'sent ${row['sent_utc']} · ${row['body_chars']} chars · '
          'body ${_short(row['body_sha256_computed'], 16)}',
          style: fwMono(t, size: 11, color: t.inkFaint),
        ),
        if (renamed)
          Text('the file name disagrees with the header inside it',
              style: fwMono(t, size: 11, color: t.drift)),
      ],
    );
  }
}
