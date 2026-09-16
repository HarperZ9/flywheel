// Codex account surface for the Endpoints view.

import 'package:flutter/material.dart';

import '../client/codex_account_client.dart';
import '../client/gateway_client.dart';
import '../controllers/codex_account_controller.dart';
import '../models/codex_account_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class CodexAccountPanel extends StatefulWidget {
  final GatewayClient? client;
  final CodexAccountController? controller;
  final Future<bool> Function(Uri uri)? openUrl;
  final VoidCallback onAccountReady;

  const CodexAccountPanel({
    super.key,
    this.client,
    this.controller,
    this.openUrl,
    required this.onAccountReady,
  }) : assert(client != null || controller != null);

  @override
  State<CodexAccountPanel> createState() => _CodexAccountPanelState();
}

class _CodexAccountPanelState extends State<CodexAccountPanel> {
  late CodexAccountController _controller;
  late bool _ownsController;
  String _openMessage = '';

  @override
  void initState() {
    super.initState();
    _attachController();
    _controller.refresh();
  }

  @override
  void didUpdateWidget(CodexAccountPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller ||
        oldWidget.client != widget.client) {
      _detachController();
      _attachController();
      _controller.refresh();
    }
  }

  @override
  void dispose() {
    _detachController();
    super.dispose();
  }

  void _attachController() {
    _ownsController = widget.controller == null;
    _controller = widget.controller ??
        CodexAccountController(GatewayCodexAccountClient(widget.client!));
    _controller.addListener(_changed);
  }

  void _detachController() {
    _controller.removeListener(_changed);
    if (_ownsController) _controller.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _start(CodexLoginMode mode) async {
    _openMessage = '';
    await _controller.startLogin(mode);
    if (mounted) setState(() {});
  }

  Future<void> _checkResult() async {
    final ready = await _controller.refreshLoginResult();
    if (ready && mounted) widget.onAccountReady();
  }

  Future<void> _openReturnedUrl() async {
    final uri = _controller.login?.launchUri;
    if (uri == null) return;
    final opener = widget.openUrl;
    final opened = opener != null && await opener(uri);
    if (!mounted) return;
    setState(() {
      _openMessage = opened
          ? 'Opening the returned Codex sign-in URL.'
          : 'Could not open the returned Codex sign-in URL.';
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final c = _controller;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(child: Kicker('Codex account', hot: true)),
          VerdictPill(_phaseLabel(c.phase), status: _phaseStatus(c.phase)),
        ]),
        const SizedBox(height: FwLayout.s3),
        Text(c.account?.primaryRouteLabel ?? 'Codex account unavailable',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: FwLayout.s2),
        Text(c.account?.chatGptLabel ?? 'ChatGPT account state unknown',
            style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
        if (c.message.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text(c.message, style: fwMono(t, size: 11.5, color: t.inkFaint)),
        ],
        if (c.login != null) ...[
          const SizedBox(height: FwLayout.s3),
          _PendingLogin(controller: c),
        ],
        const SizedBox(height: FwLayout.s3),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          FilledButton(
            style: _buttonStyle(),
            onPressed: c.busy ? null : () => _start(CodexLoginMode.browser),
            child: Text(c.busy ? 'Working…' : 'Start browser sign-in'),
          ),
          OutlinedButton(
            style: _buttonStyle(),
            onPressed: c.busy ? null : () => _start(CodexLoginMode.deviceCode),
            child: const Text('Use device code'),
          ),
          if (c.login != null) ...[
            OutlinedButton(
              style: _buttonStyle(),
              onPressed: c.busy ? null : _openReturnedUrl,
              child: const Text('Open returned URL'),
            ),
            TextButton(
              style: _buttonStyle(),
              onPressed: c.busy ? null : _checkResult,
              child: const Text('Check result'),
            ),
            TextButton(
              style: _buttonStyle(),
              onPressed: c.busy ? null : () => _controller.cancelLogin(),
              child: const Text('Cancel login'),
            ),
          ],
          if (c.phase == CodexAccountPhase.signedIn)
            TextButton(
              style: _buttonStyle(),
              onPressed: c.busy ? null : () => _controller.logout(),
              child: const Text('Logout'),
            ),
        ]),
        if (_openMessage.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text(_openMessage, style: TextStyle(fontSize: 12, color: t.inkMuted)),
        ],
        if (c.catalog != null) ...[
          const SizedBox(height: FwLayout.s3),
          _ModelSummary(catalog: c.catalog!),
        ],
      ]),
    );
  }

  ButtonStyle _buttonStyle() => ButtonStyle(
        minimumSize: const WidgetStatePropertyAll(Size(44, 44)),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      );
}

class _PendingLogin extends StatelessWidget {
  final CodexAccountController controller;
  const _PendingLogin({required this.controller});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final login = controller.login!;
    return Container(
      padding: const EdgeInsets.all(FwLayout.s3),
      decoration: BoxDecoration(
        color: t.ground2,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: t.hairline),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(login.loginId, style: fwMono(t, size: 11.5)),
        if (login.userCode.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s2),
          Text(login.userCode,
              style: fwMono(t, size: 15, weight: FontWeight.w700)),
        ],
      ]),
    );
  }
}

class _ModelSummary extends StatelessWidget {
  final CodexModelCatalog catalog;
  const _ModelSummary({required this.catalog});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (catalog.models.isEmpty) {
      return HonestNull(catalog.reason.isEmpty
          ? 'No Codex model catalog was returned.'
          : catalog.reason);
    }
    final names = catalog.models.take(3).map((m) => m.id).join(', ');
    return Text('Model catalog: $names',
        style: fwMono(t, size: 11.5, color: t.inkMuted));
  }
}

String _phaseLabel(CodexAccountPhase phase) => switch (phase) {
      CodexAccountPhase.signedIn => 'account ready',
      CodexAccountPhase.loginPending => 'login pending',
      CodexAccountPhase.failed => 'failed',
      CodexAccountPhase.signedOut => 'sign-in needed',
      CodexAccountPhase.unavailable => 'unavailable',
    };

String _phaseStatus(CodexAccountPhase phase) => switch (phase) {
      CodexAccountPhase.signedIn => 'verified',
      CodexAccountPhase.signedOut => 'unverifiable',
      CodexAccountPhase.loginPending => 'unverifiable',
      CodexAccountPhase.failed => 'drift',
      CodexAccountPhase.unavailable => 'drift',
    };
