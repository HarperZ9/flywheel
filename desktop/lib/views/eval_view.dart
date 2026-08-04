// eval_view.dart — the Eval destination: the signed eval-run receipt, live.
//
// The primary product wedge, made operable. Pick an endpoint (and optionally
// which model it serves), run a real eval, and get a sealed receipt that binds
// the outcome to endpoint, model, dataset digest, config, and judge. Verify it
// offline; corrupt one byte and the same verifier refuses. This view is a thin
// wire: it loads the endpoint roster and hands the client's typed eval methods
// to the dumb panel, which owns the on-stage run/verify/refuse flow.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/eval_receipt_panel.dart';
import '../widgets/fw.dart';

class EvalView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  const EvalView({super.key, required this.client, required this.alive});

  @override
  State<EvalView> createState() => _EvalViewState();
}

class _EvalViewState extends State<EvalView> {
  List<EndpointRow> _endpoints = [];
  String? _endpoint;
  // per-endpoint model override, session-lived; absent means the default
  final Map<String, String> _chosenModels = {};

  @override
  void initState() {
    super.initState();
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(EvalView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _loadEndpoints();
  }

  Future<void> _loadEndpoints() async {
    if (!widget.alive) return;
    try {
      final rows = await widget.client.endpointRoster();
      if (mounted) setState(() => _endpoints = rows);
    } catch (_) {/* the panel degrades to copy without a roster */}
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
          'The engine is offline. Run an eval once it is up.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(storageKey: 'eval', children: [
      const SectionHeader('Signed eval receipts', kicker: 'eval'),
      const SizedBox(height: FwLayout.s3),
      Text(
        'A real eval run through a real provider, sealed into a receipt that '
        'binds the outcome to endpoint, model, dataset digest, config, and '
        'judge. Verify it offline; corrupt one byte and the verifier refuses.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s5),
      EvalReceiptPanel(
        endpoints: _endpoints,
        endpoint: _endpoint,
        model: _endpoint == null ? null : _chosenModels[_endpoint],
        onEndpoint: (v) => setState(() => _endpoint = v),
        onModel: (v) => setState(() => v.isEmpty
            ? _chosenModels.remove(_endpoint)
            : _chosenModels[_endpoint!] = v),
        loadModels: () => widget.client.models(_endpoint ?? ''),
        onRun: () => widget.client.evalRun(
          _endpoint ?? '',
          model: _endpoint == null ? null : _chosenModels[_endpoint],
          n: 3,
        ),
        onVerify: (receipt) => widget.client.evalVerify(receipt),
      ),
    ]);
  }
}
