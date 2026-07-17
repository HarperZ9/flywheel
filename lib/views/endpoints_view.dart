// endpoints_view.dart — the Endpoints view: the universal router's roster.
// Local tiers get a real health probe; hosted providers show credential
// presence only (the env var name, never a value); the scoreboard shows
// observed routing outcomes, not promises.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/endpoint_models.dart';
import '../models/gateway_models.dart';
import '../models/render_status.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/charts.dart';
import '../widgets/fw.dart';
import '../widgets/keys_panel.dart';
import '../widgets/training_card.dart';

class EndpointsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const EndpointsView({super.key, required this.client, required this.alive});

  @override
  State<EndpointsView> createState() => _EndpointsViewState();
}

class _EndpointsViewState extends State<EndpointsView> {
  EndpointHealthDoc? _health;
  List<EndpointRow> _roster = [];
  List<ProviderScore> _scores = [];
  Map<String, dynamic>? _training;
  Map<String, dynamic>? _keychain;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(EndpointsView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _load();
  }

  Future<void> _load() async {
    if (!widget.alive) return;
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        widget.client.endpointHealth(),
        widget.client.endpointRoster(),
        widget.client.routerStats(),
        widget.client.trainingStatus(),
        widget.client.keychainRoster(),
      ]);
      if (mounted) {
        setState(() {
          _health = EndpointHealthDoc.fromJson(
              results[0] as Map<String, dynamic>);
          _roster = results[1] as List<EndpointRow>;
          _scores =
              ProviderScore.listFromStats(results[2] as Map<String, dynamic>);
          _training = results[3] as Map<String, dynamic>;
          _keychain = results[4] as Map<String, dynamic>;
          _error = null;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = '$e';
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The router roster appears when it runs.',
          command: 'flywheel up');
    }
    if (_error != null) return FwEmpty('The roster could not be read: $_error');
    if (_health == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    }
    final h = _health!;
    final t = context.fw;
    return ViewScroll(
      children: [
        SectionHeader(
          'Endpoints',
          kicker: 'one request shape, every provider',
          trailing: OutlinedButton(
            onPressed: _loading ? null : _load,
            child: Text(_loading ? 'Probing…' : 'Probe'),
          ),
        ),
        const SizedBox(height: FwLayout.s4),
        Row(
          children: [
            Expanded(
                child: StatTile(
                    label: 'local healthy',
                    value: '${h.localHealthy}/${h.localTotal}',
                    status: fractionStatus(h.localHealthy, h.localTotal))),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child: StatTile(
                    label: 'keys present',
                    value: '${h.hostedConfigured}/${h.hosted.length}')),
            const SizedBox(width: FwLayout.s3),
            Expanded(
                child:
                    StatTile(label: 'providers', value: '${_roster.length}')),
          ],
        ),
        const SizedBox(height: FwLayout.s5),
        const Kicker('local tiers · probed live', hot: true),
        const SizedBox(height: FwLayout.s3),
        Row(
          children: [
            for (final l in h.local) ...[
              Expanded(child: _localCard(t, l)),
              if (l != h.local.last) const SizedBox(width: FwLayout.s3),
            ],
          ],
        ),
        if (_training != null && _training!['error'] == null) ...[
          const SizedBox(height: FwLayout.s3),
          TrainingCard(training: _training!),
        ],
        const SizedBox(height: FwLayout.s5),
        const Kicker('providers · credential presence only, never values'),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s4, vertical: FwLayout.s2),
          child: Column(
            children: [for (final r in _roster) _providerRow(t, r)],
          ),
        ),
        if (_keychain != null &&
            ((_keychain!['entries'] ?? []) as List).isNotEmpty) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('keys · stored in the OS keychain, shown as presence'),
          const SizedBox(height: FwLayout.s3),
          KeysPanel(
            doc: _keychain!,
            onSet: widget.client.keychainSet,
            onDelete: widget.client.keychainDelete,
            onChanged: _load,
          ),
        ],
        const SizedBox(height: FwLayout.s5),
        const Kicker('scoreboard · observed routing outcomes'),
        const SizedBox(height: FwLayout.s3),
        if (_scores.isEmpty)
          const HonestNull(
              'No routed traffic recorded yet. The scoreboard fills from '
              'real outcomes as prompts route; nothing here is a promise.')
        else
          HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s4, vertical: FwLayout.s2),
            child: Column(
              children: [for (final s in _scores) _scoreRow(t, s)],
            ),
          ),
      ],
    );
  }

  Widget _localCard(FwTokens t, LocalTier l) {
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              VerdictDot(l.healthy ? 'healthy' : 'missing', size: 7),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: Text(l.name,
                    style: const TextStyle(
                        fontSize: 13.5, fontWeight: FontWeight.w600)),
              ),
              Text(l.kind, style: fwMono(t, size: 10.5, color: t.inkFaint)),
            ],
          ),
          if (l.detail.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s2),
            Text(l.detail,
                overflow: TextOverflow.ellipsis,
                style: fwMono(t, size: 11, color: t.inkMuted)),
          ],
        ],
      ),
    );
  }

  Widget _providerRow(FwTokens t, EndpointRow r) {
    final (label, status) = switch (r.credential) {
      'present' => ('key present', 'verified'),
      'cli-auth' => ('cli auth', 'verified'),
      'local-none' => ('local', 'verified'),
      _ => ('no key', 'absent'),
    };
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          SizedBox(
            width: 170,
            child: Text(r.name,
                style: fwMono(t, size: 12, weight: FontWeight.w600)),
          ),
          Expanded(
            child: Text(r.providerRole.isNotEmpty ? r.providerRole : r.backend,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12, color: t.inkMuted)),
          ),
          VerdictPill(label, status: status),
        ],
      ),
    );
  }

  Widget _scoreRow(FwTokens t, ProviderScore s) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          SizedBox(
            width: 170,
            child: Text(s.name,
                style: fwMono(t, size: 12, weight: FontWeight.w600)),
          ),
          _cell(t, '${s.attempts} tried'),
          MiniBar(s.successRate,
              status: s.successRate >= 0.5 ? 'verified' : 'drift'),
          const SizedBox(width: FwLayout.s3),
          _cell(t, '${(s.successRate * 100).toStringAsFixed(0)}% ok'),
          _cell(t, '${s.meanLatency.toStringAsFixed(1)}s'),
          const Spacer(),
          if (s.circuitOpen)
            const VerdictPill('circuit open', status: 'drift')
          else
            Text('score ${s.score.toStringAsFixed(2)}',
                style: fwMono(t, size: 11, color: t.inkMuted)),
        ],
      ),
    );
  }

  Widget _cell(FwTokens t, String text) => SizedBox(
        width: 90,
        child: Text(text, style: fwMono(t, size: 11.5, color: t.inkMuted)),
      );

}
