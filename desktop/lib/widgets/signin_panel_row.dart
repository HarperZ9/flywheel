part of 'signin_panel.dart';

extension _SigninPanelRows on _SigninPanelState {
  Widget _row(FwTokens t, Map<String, dynamic> p) {
    final provider = '${p['provider']}';
    final kind = '${p['kind']}';
    final officialCli = kind == 'official-cli';
    final officialApp = kind == 'official-app-server';
    final official = officialCli || officialApp;
    final accountKey = officialApp ? 'official_app_server' : 'official_cli';
    final account = (p[accountKey] is Map)
        ? Map<String, dynamic>.from(p[accountKey] as Map)
        : <String, dynamic>{};
    final accountState =
        '${account['account_state'] ?? account['state'] ?? p['source'] ?? 'unknown'}';
    final accountAuth =
        account['authenticated'] == true || p['present'] == true;
    final present = official ? accountAuth : p['present'] == true;
    final pending = p['pending'] == true;
    final open = !official && _guided == provider;
    final deviceOpen = _deviceProvider == provider;
    final waitText = official
        ? (officialApp ? 'waiting for ChatGPT' : 'waiting for Claude Code')
        : 'waiting for the browser';
    final buttonText = official ? 'Open sign-in' : 'Sign in';
    final accountText = _accountText(
        officialApp: officialApp,
        authenticated: accountAuth,
        state: accountState,
        account: account);
    final canCheckRoute = officialApp &&
        accountAuth &&
        account['route_ready'] != true &&
        account['readiness_check_available'] == true &&
        widget.onCheckExecution != null;
    final checkingRoute = _routeCheckProvider == provider;
    final headerActions = <Widget>[
      if (pending) ...[
        Text(waitText, style: fwMono(t, size: 10, color: t.inkMuted)),
        if (widget.onCancel != null)
          TextButton(
            onPressed: _busy ? null : () => _out(provider, cancel: true),
            child: const Text('Cancel'),
          ),
      ] else if (present && !official)
        TextButton(
          onPressed: _busy ? null : () => _out(provider),
          child: const Text('Sign out'),
        )
      else if (present && officialApp) ...[
        if (canCheckRoute)
          TextButton(
            onPressed:
                _busy || checkingRoute ? null : () => _checkExecution(provider),
            child: const Text('Check route'),
          ),
        TextButton(
          onPressed: _busy ? null : () => _out(provider),
          child: const Text('Sign out'),
        ),
      ] else if (present && official)
        TextButton(
          onPressed: _busy ? null : widget.onChanged,
          child: const Text('Refresh'),
        )
      else
        FilledButton(
          onPressed: _busy ? null : () => _start(provider),
          child: Text(buttonText),
        ),
    ];
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: FwLayout.s2,
              runSpacing: FwLayout.s1,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    VerdictDot(
                        official && accountAuth ? 'verified' : 'unverifiable',
                        size: 7),
                    const SizedBox(width: FwLayout.s2),
                    Text(provider,
                        style: const TextStyle(
                            fontSize: 13, fontWeight: FontWeight.w600)),
                    const SizedBox(width: FwLayout.s2),
                    Text('${p['kind_label'] ?? kind}',
                        style: fwMono(t, size: 10, color: t.inkFaint)),
                  ],
                ),
                ...headerActions,
              ],
            ),
            const SizedBox(height: FwLayout.s2),
            if (official)
              Text(accountText)
            else ...[
              if (!pending && p['last'] == 'done' && present)
                const Text('credential stored'),
              if (present)
                const Text('credential present; authentication unverified'),
            ],
            if (p['last'] == 'cancelled')
              const Text('sign-in cancelled locally'),
            Text('${p['sanction'] ?? ''}',
                style: TextStyle(fontSize: 11, color: t.inkFaint)),
            if (present && !official)
              Padding(
                padding: const EdgeInsets.only(top: FwLayout.s1),
                child: Text('token in ${p['source']}:${p['keychain_name']}',
                    style: fwMono(t, size: 10, color: t.inkMuted)),
              ),
            if ('${p['last_error'] ?? ''}'.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: FwLayout.s1),
                child: Text('${p['last_error']}',
                    style: fwMono(t, size: 10, color: t.drift)),
              ),
            if (open) ...[
              const SizedBox(height: FwLayout.s3),
              for (var i = 0; i < _steps.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text('${i + 1}. ${_steps[i]}',
                      style: TextStyle(fontSize: 11.5, color: t.ink)),
                ),
              const SizedBox(height: FwLayout.s2),
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: _paste,
                    obscureText: true,
                    autocorrect: false,
                    enableSuggestions: false,
                    style: fwMono(t, size: 11),
                    decoration: const InputDecoration(
                        isDense: true,
                        hintText: 'Paste the token the tool printed'),
                    onSubmitted: (_) => _submit(provider),
                  ),
                ),
                const SizedBox(width: FwLayout.s2),
                FilledButton(
                  onPressed: _busy ? null : () => _submit(provider),
                  child: const Text('Store'),
                ),
                TextButton(
                  onPressed: _busy ? null : _closeGuided,
                  child: const Text('Cancel'),
                ),
              ]),
            ],
            if (deviceOpen) ...[
              const SizedBox(height: FwLayout.s3),
              Text('Open $_deviceUrl',
                  softWrap: true,
                  style: fwMono(t, size: 10.5, color: t.inkMuted)),
              const SizedBox(height: FwLayout.s1),
              Text('Code: $_deviceCode',
                  style: fwMono(t, size: 13, color: t.ink)),
              if (widget.onCancel != null)
                TextButton(
                  onPressed: _busy ? null : () => _out(provider, cancel: true),
                  child: const Text('Cancel'),
                ),
            ],
          ],
        ),
      ),
    );
  }

  Map<String, dynamic>? _provider(String provider) {
    final providers = ((widget.doc['providers'] ?? []) as List)
        .whereType<Map<String, dynamic>>();
    for (final p in providers) {
      if ('${p['provider']}' == provider) return p;
    }
    return null;
  }

  bool _trustedSignInUrl(String kind, String value) {
    final uri = Uri.tryParse(value);
    if (uri == null || uri.scheme != 'https') return false;
    if (kind != 'official-app-server') return true;
    final host = uri.host.toLowerCase();
    return host == 'openai.com' ||
        host == 'chatgpt.com' ||
        host.endsWith('.openai.com') ||
        host.endsWith('.chatgpt.com');
  }

  String _accountText({
    required bool officialApp,
    required bool authenticated,
    required String state,
    required Map<String, dynamic> account,
  }) {
    if (officialApp) {
      if (authenticated) {
        final plan = '${account['plan_type'] ?? ''}';
        return plan.isEmpty
            ? 'ChatGPT account connected'
            : 'ChatGPT account connected · plan: $plan';
      }
      return switch (state) {
        'not_authenticated' => 'ChatGPT account not signed in',
        'cli_absent' => 'Codex CLI absent',
        'wrapper_unsupported' => 'Codex CLI wrapper unsupported',
        _ => 'Codex app-server account unknown',
      };
    }
    return authenticated
        ? 'Claude Code account authenticated'
        : switch (state) {
            'not_authenticated' => 'Claude Code account not signed in',
            'cli_absent' => 'Claude Code CLI absent',
            'wrapper_unsupported' => 'Claude Code wrapper unsupported',
            _ => 'Claude Code account unknown',
          };
  }
}
