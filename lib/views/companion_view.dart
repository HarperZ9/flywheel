// companion_view.dart — the Companion view: ask once, the seat answers from
// the cheapest honest source. Cache and locally-verified answers carry a
// verified chip; consensus is labeled as agreement, not proof; hard prompts
// escalate with the failed local attempt on record. The chip never lies.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
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
  _Turn(this.prompt);
}

class _CompanionViewState extends State<CompanionView> {
  final _controller = TextEditingController();
  final _scroll = ScrollController();
  final List<_Turn> _turns = [];

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
            _answerCard(context, turn.result!),
        ],
      ),
    );
  }

  Widget _answerCard(BuildContext context, CompanionResult r) {
    final t = context.fw;
    final (chip, status, note) = switch (r.source) {
      'cache' => ('verified · cache', 'verified', null),
      'local-verified' => ('verified · local', 'verified', null),
      'local-consensus' => (
          'consensus · local',
          'unverifiable',
          'Agreement across local samples, not a proof. Treat accordingly.'
        ),
      'escalate' => (
          'escalate → ${r.escalateTo ?? 'frontier'}',
          'drift',
          'The local model could not verify an answer. The failed attempt is '
              'on the ledger; route this prompt to a stronger endpoint.'
        ),
      _ => (r.source, 'unverifiable', null),
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
          ScaffoldStrip(r.scaffold),
        ],
      ),
    );
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
