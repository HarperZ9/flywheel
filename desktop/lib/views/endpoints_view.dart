// endpoints_view.dart — the Endpoints view: the universal router's roster.
// Local tiers get a real health probe; hosted providers show credential
// presence only (the env var name, never a value); the scoreboard shows
// observed routing outcomes, not promises.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../client/gateway_client.dart';
import '../models/endpoint_models.dart';
import '../models/gateway_models.dart';
import '../models/render_status.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/endpoint_details.dart';
import '../widgets/fw.dart';
import '../widgets/keys_panel.dart';
import '../widgets/session_tokens_panel.dart';
import '../widgets/signin_panel.dart';
import '../widgets/training_card.dart';

class EndpointsView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const EndpointsView({super.key, required this.client, required this.alive});

  @override
  State<EndpointsView> createState() => _EndpointsViewState();
}

class _EndpointsViewState extends State<EndpointsView> {
  final bool _mobile = Platform.isAndroid || Platform.isIOS;
  EndpointHealthDoc? _health;
  List<EndpointRow> _roster = [];
  List<ProviderScore> _scores = [];
  Map<String, dynamic>? _training;
  Map<String, dynamic>? _keychain;
  Map<String, dynamic>? _auth;
  Map<String, dynamic>? _sessionTokens;
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
        widget.client.getJson('/api/auth'),
        widget.client.sessionTokens(),
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
          _auth = results[5] as Map<String, dynamic>;
          _sessionTokens = results[6] as Map<String, dynamic>;
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
        AdaptiveTiles(children: [
          StatTile(
              label: 'local healthy',
              value: '${h.localHealthy}/${h.localTotal}',
              status: fractionStatus(h.localHealthy, h.localTotal)),
          StatTile(
              label: 'subscriptions',
              value: '${h.subscriptionAvailable}',
              status: h.subscriptionAvailable > 0 ? 'verified' : null),
          StatTile(
              label: 'keys present',
              value: '${h.hostedConfigured}/${h.hosted.length}'),
        ]),
        const SizedBox(height: FwLayout.s5),
        const Kicker('local tiers · probed live', hot: true),
        const SizedBox(height: FwLayout.s3),
        AdaptiveTiles(
          children: [for (final l in h.local) _localCard(t, l)],
        ),
        if (_training != null && _training!['error'] == null) ...[
          const SizedBox(height: FwLayout.s3),
          TrainingCard(training: _training!),
        ],
        const SizedBox(height: FwLayout.s5),
        const Kicker('providers · credential presence only, never values'),
        const SizedBox(height: FwLayout.s3),
        ProviderRoster(roster: _roster),
        if (_auth != null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('sign in · a subscription can carry usage'),
          const SizedBox(height: FwLayout.s3),
          SigninPanel(
            doc: _auth!,
            onLogin: (p) => widget.client.postJson('/api/auth/login', {
              'provider': p,
              if (_mobile) 'callback_base': widget.client.baseUrl,
            }),
            onOpenUrl: _mobile ? _openSignInUrl : null,
            onToken: (p, token) => widget.client
                .postJson('/api/auth/token', {'provider': p, 'token': token}),
            onLogout: (p) => widget.client
                .postJson('/api/auth/logout', {'provider': p}),
            onChanged: _load,
          ),
        ],
        if (_sessionTokens != null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('session tokens · scoped, time-bounded agent credentials'),
          const SizedBox(height: FwLayout.s3),
          SessionTokensPanel(
            doc: _sessionTokens!,
            onRevoke: widget.client.sessionTokenRevoke,
            onChanged: _load,
          ),
        ],
        if (_keychain != null) ...[
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
        EndpointScoreboard(scores: _scores),
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

  Future<bool> _openSignInUrl(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return false;
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      return false;
    }
  }
}
