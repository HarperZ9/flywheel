// usage_view.dart — the Usage destination: signed, offline-verifiable spend.
//
// Every routed answer carries an auditable record of what it cost. Peer CLIs
// show a locally computed dollar estimate their own docs disclaim, or show
// nothing; none sign or attest usage. Flywheel binds the provider-reported
// token counts and the model reference into a sealed receipt a stranger
// re-verifies offline, and is honest about which number is which: the tokens are
// provider-reported when the provider returned them (else a labeled estimate),
// and the dollar figure is a table lookup, never a provider-billed number. This
// view is a thin wire: it hands the client's typed usage methods to the panel.

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import '../client/gateway_client.dart';
import '../models/usage_live_selection.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import '../widgets/usage_receipt_panel.dart';
import '../widgets/usage_live_panel.dart';

class UsageView extends StatelessWidget {
  final GatewayClient client;
  final bool alive;
  final ValueListenable<UsageLiveSelection>? usageSelection;
  const UsageView(
      {super.key,
      required this.client,
      required this.alive,
      this.usageSelection});

  @override
  Widget build(BuildContext context) {
    if (!alive) {
      return const FwEmpty(
          'The engine is offline. Route an answer, then meter its spend here.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return ViewScroll(storageKey: 'usage', children: [
      const SectionHeader('Usage metering', kicker: 'usage'),
      const SizedBox(height: FwLayout.s4),
      _livePanel(),
      const SizedBox(height: FwLayout.s5),
      const SizedBox(height: FwLayout.s3),
      Text(
        'Every answer costs something, and a stranger should be able to re-check '
        'what it cost. Each routed answer seals a usage receipt binding the '
        'provider-reported token counts and the model reference; the dollar '
        'figure is a table lookup, never a provider-billed number, and a local '
        'endpoint records no dollar figure at all rather than inventing one. '
        'VERIFY re-checks a receipt offline — MATCH is the accept mark.',
        style: TextStyle(fontSize: 13, height: 1.5, color: t.inkMuted),
      ),
      const SizedBox(height: FwLayout.s5),
      UsageReceiptPanel(
        loadSummary: () => client.usageSummary(),
        onVerify: (receipt) => client.usageVerify(receipt),
      ),
    ]);
  }

  Widget _livePanel() {
    final listenable = usageSelection;
    if (listenable == null) {
      return _livePanelFor(UsageLiveSelection.none);
    }
    return ValueListenableBuilder<UsageLiveSelection>(
        valueListenable: listenable,
        builder: (_, selection, __) => _livePanelFor(selection));
  }

  Widget _livePanelFor(UsageLiveSelection selection) => UsageLivePanel(
      key: ValueKey(selection.cacheKey),
      loadSnapshot: () => client.getJson(selection.path));
}
