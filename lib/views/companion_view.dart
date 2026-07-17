// companion_view.dart — the Companion view: ask once, the seat answers from
// the cheapest honest source. Cache and locally-verified answers carry a
// verified chip; consensus is labeled as agreement, not proof; hard prompts
// escalate with the failed local attempt on record. The chip never lies.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/render_status.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/model_picker.dart';
import '../widgets/scaffold_strip.dart';

class CompanionView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const CompanionView({super.key, required this.client, required this.alive});

  @override
  State<CompanionView> createState() => _CompanionViewState();
}

class _Turn {
  final String prompt;
  CompanionResult? result;
  String? error;
  bool pending = true;
  // the escalate branch: a real route to a stronger endpoint, with receipt
  String? routeEndpoint;
  bool routing = false;
  Map<String, dynamic>? routed;
  String? routeError;
  _Turn(this.prompt);
}

class _CompanionViewState extends State<CompanionView> {
  final _controller = TextEditingController();
  final _scroll = ScrollController();
  final List<_Turn> _turns = [];
  List<EndpointRow> _endpoints = [];

  @override
  void initState() {
    super.initState();
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(CompanionView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _loadEndpoints();
  }

  Future<void> _loadEndpoints() async {
    if (!widget.alive) return;
    try {
      final rows = await widget.client.endpointRoster();
      if (mounted) setState(() => _endpoints = rows);
    } catch (_) {/* the escalate card degrades to copy without a roster */}
  }

  Future<void> _route(_Turn turn) async {
    final endpoint = turn.routeEndpoint;
    if (endpoint == null || turn.routing) return;
    setState(() {
      turn.routing = true;
      turn.routeError = null;
    });
    try {
      final r = await widget.client.route(turn.prompt, endpoint);
      if (mounted) setState(() => turn.routed = r);
    } catch (e) {
      if (mounted) setState(() => turn.routeError = '$e');
    } finally {
      if (mounted) setState(() => turn.routing = false);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final prompt = _controller.text.trim();
    if (prompt.isEmpty || !widget.alive) return;
    final turn = _Turn(prompt);
    setState(() {
      _turns.add(turn);
      _controller.clear();
    });
    _scrollToEnd();
    try {
      final r = await widget.client.companion(prompt);
      setState(() {
        turn.result = r;
        turn.pending = false;
      });
    } catch (e) {
      setState(() {
        turn.error = '$e';
        turn.pending = false;
      });
    }
    _scrollToEnd();
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent,
            duration: FwLayout.transition, curve: Curves.easeOut);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. The companion seat appears when it runs.',
          command: 'flywheel up');
    }
    return Column(
      children: [
        Expanded(
          child: _turns.isEmpty
              ? const FwEmpty(
                  'Ask once. Verified and cached answers come from the local '
                  'model; agreement without proof is labeled consensus; hard '
                  'prompts escalate with the failed local attempt on record.')
              : ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.symmetric(
                      horizontal: FwLayout.s6, vertical: FwLayout.s5),
                  itemCount: _turns.length,
                  itemBuilder: (ctx, i) => _turnBlock(ctx, _turns[i]),
                ),
        ),
        _inputBar(context),
      ],
    );
  }

  Widget _turnBlock(BuildContext context, _Turn turn) {
    final t = context.fw;
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s5),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('you'),
          const SizedBox(height: FwLayout.s1),
          Text(turn.prompt, style: Theme.of(context).textTheme.bodyLarge),
          const SizedBox(height: FwLayout.s3),
          if (turn.pending)
            Text('routing…', style: fwMono(t, size: 11.5, color: t.inkFaint))
          else if (turn.error != null)
            HonestNull('The request failed: ${turn.error}')
          else
            _answerCard(context, turn),
        ],
      ),
    );
  }

  Widget _answerCard(BuildContext context, _Turn turn) {
    final r = turn.result!;
    final t = context.fw;
    // the chip LABEL and note describe the transport (cache/local/escalate),
    // but the COLOR is the engine's own verdict on the answer, not the source:
    // a cache hit or a local run is transport, not an acceptance.
    final status = companionStatus(r.verdict);
    final (chip, note) = switch (r.source) {
      'cache' => ('verified · cache', null),
      'local-verified' => ('verified · local', null),
      'local-consensus' => (
          'consensus · local',
          'Agreement across local samples, not a proof. Treat accordingly.'
        ),
      'escalate' => (
          'escalate → ${r.escalateTo ?? 'frontier'}',
          'The local model could not verify an answer. The failed attempt is '
              'on the ledger; route this prompt to a stronger endpoint.'
        ),
      _ => (r.source, null),
    };
    final body = r.text ?? r.bestEffortText;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              VerdictPill(chip, status: status),
              if (r.source == 'escalate' && body != null) ...[
                const SizedBox(width: FwLayout.s2),
                VerdictPill('best effort, unverified',
                    status: 'unverifiable'),
              ],
            ],
          ),
          if (body != null) ...[
            const SizedBox(height: FwLayout.s3),
            SelectableText(body,
                style: fwMono(t, size: 12.5).copyWith(height: 1.55)),
          ],
          if (note != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull(note),
          ],
          if (r.receipt != null && r.receipt!.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            HashText('receipt', r.receipt!, keep: 32),
          ],
          if (r.source == 'escalate') ...[
            const SizedBox(height: FwLayout.s3),
            _escalateRow(t, turn),
          ],
          ScaffoldStrip(r.scaffold),
        ],
      ),
    );
  }

  /// The escalate branch made operable: pick a stronger endpoint from the
  /// roster and actually route the prompt, receipt included.
  Widget _escalateRow(FwTokens t, _Turn turn) {
    final routed = turn.routed;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        if (_endpoints.isNotEmpty)
          ModelPickerButton(
            endpoints: _endpoints,
            current: turn.routeEndpoint,
            enabled: !turn.routing,
            onSelect: (v) => setState(() => turn.routeEndpoint = v),
          )
        else
          Text('no endpoints in the roster',
              style: fwMono(t, size: 11, color: t.inkFaint)),
        const SizedBox(width: FwLayout.s3),
        FilledButton.tonal(
          onPressed: (turn.routeEndpoint == null || turn.routing)
              ? null
              : () => _route(turn),
          child: Text(turn.routing ? 'Routing…' : 'Route it'),
        ),
      ]),
      if (turn.routeError != null) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull('Route failed: ${turn.routeError}'),
      ],
      if (routed != null) ...[
        const SizedBox(height: FwLayout.s3),
        VerdictPill('routed · ${turn.routeEndpoint}', status: 'drift'),
        const SizedBox(height: FwLayout.s2),
        SelectableText('${routed['text'] ?? routed['error'] ?? ''}',
            style: fwMono(t, size: 12.5).copyWith(height: 1.55)),
        if ('${routed['receipt'] ?? ''}'.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          HashText('receipt', '${routed['receipt']}', keep: 32),
        ],
      ],
    ]);
  }

  Widget _inputBar(BuildContext context) {
    final t = context.fw;
    return Container(
      padding: const EdgeInsets.all(FwLayout.s4),
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(top: BorderSide(color: t.line)),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _controller,
              maxLines: 3,
              minLines: 1,
              style: const TextStyle(fontSize: 13.5),
              decoration:
                  const InputDecoration(hintText: 'Ask the companion…'),
              onSubmitted: (_) => _send(),
            ),
          ),
          const SizedBox(width: FwLayout.s3),
          FilledButton(onPressed: _send, child: const Text('Send')),
        ],
      ),
    );
  }
}
