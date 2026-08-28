// companion_view.dart â€” the Companion view: ask once, the seat answers from
// the cheapest honest source. Cache and locally-verified answers carry a
// verified chip; consensus is labeled as agreement, not proof; hard prompts
// escalate with the failed local attempt on record. The chip never lies.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../models/render_status.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/escalate_row.dart';
import '../widgets/companion_input_bar.dart';
import '../widgets/fw.dart';
import '../widgets/operation_grant_sheet.dart';
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
  // per-endpoint model override, session-lived; absent means the default
  final Map<String, String> _chosenModels = {};

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
      final requestId =
          'companion-route-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<Map<String, dynamic>>(
        context,
        GatewayOperation.routeSend(requestId, turn.prompt, endpoint,
            model: _chosenModels[endpoint]),
        (body) => widget.client.route(turn.prompt, endpoint,
            model: _chosenModels[endpoint], authorizedBody: body),
        currentOperation: () => null,
      );
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
      final requestId =
          'companion-ask-${DateTime.now().microsecondsSinceEpoch}';
      final r = await authorizeGatewayOperation<CompanionResult>(
        context,
        GatewayOperation.companionAsk(requestId, prompt),
        (body) => widget.client.companion(prompt, authorizedBody: body),
        currentOperation: () => null,
      );
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
              : LayoutBuilder(builder: (context, box) {
                  final pad = box.maxWidth < 480 ? FwLayout.s4 : FwLayout.s6;
                  return ListView.builder(
                    controller: _scroll,
                    padding: EdgeInsets.symmetric(
                        horizontal: pad, vertical: FwLayout.s5),
                    itemCount: _turns.length,
                    itemBuilder: (ctx, i) => _turnBlock(ctx, _turns[i]),
                  );
                }),
        ),
        CompanionInputBar(controller: _controller, onSend: _send),
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
            Text('routingâ€¦', style: fwMono(t, size: 11.5, color: t.inkFaint))
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
      'cache' => ('verified Â· cache', null),
      'local-verified' => ('verified Â· local', null),
      'local-consensus' => (
          'consensus Â· local',
          'Agreement across local samples, not a proof. Treat accordingly.'
        ),
      'escalate' => (
          'escalate â†’ ${r.escalateTo ?? 'frontier'}',
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
            EscalateRouteRow(
              endpoints: _endpoints,
              endpoint: turn.routeEndpoint,
              model: turn.routeEndpoint == null
                  ? null
                  : _chosenModels[turn.routeEndpoint],
              routing: turn.routing,
              routed: turn.routed,
              routeError: turn.routeError,
              onEndpoint: (v) => setState(() => turn.routeEndpoint = v),
              onModel: (v) => setState(() => v.isEmpty
                  ? _chosenModels.remove(turn.routeEndpoint)
                  : _chosenModels[turn.routeEndpoint!] = v),
              loadModels: () =>
                  widget.client.models(turn.routeEndpoint ?? ''),
              onRoute: () => _route(turn),
            ),
          ],
          ScaffoldStrip(r.scaffold),
        ],
      ),
    );
  }

}
