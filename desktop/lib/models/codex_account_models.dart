// Codex consumer account state from the native app-server helper.
//
// This model keeps ChatGPT subscription auth and OpenAI API-key billing as
// separate facts. It parses defensively and never treats a binary or unknown
// account state as authenticated.

import 'codex_account_url_safety.dart';

enum CodexAccountPhase {
  unavailable,
  signedOut,
  signedIn,
  loginPending,
  failed
}

enum CodexLoginMode { browser, deviceCode }

class CodexAccountDoc {
  final String state, effectiveAuthSource, reason;
  final CodexConsumerAccount consumer;
  final CodexApiKeyState apiKey;
  final CodexCapabilities capabilities;
  final bool usableForCodex;

  const CodexAccountDoc({
    required this.state,
    required this.effectiveAuthSource,
    required this.reason,
    required this.consumer,
    required this.apiKey,
    required this.capabilities,
    required this.usableForCodex,
  });

  factory CodexAccountDoc.fromJson(Map<String, dynamic> json) {
    final account = _map(json['account']);
    return CodexAccountDoc(
      state: _text(json['state'], fallback: 'unavailable'),
      effectiveAuthSource: _text(account['effective_auth_source']),
      reason: _text(account['reason'] ?? json['reason']),
      consumer: CodexConsumerAccount.fromJson(_map(account['consumer'])),
      apiKey: CodexApiKeyState.fromJson(_map(account['api_key'])),
      capabilities: CodexCapabilities.fromJson(_map(json['capabilities'])),
      usableForCodex: account['usable_for_codex'] == true,
    );
  }

  factory CodexAccountDoc.unavailable(String reason) => CodexAccountDoc(
        state: 'unavailable',
        effectiveAuthSource: 'unknown',
        reason: _text(reason, fallback: 'Codex account route unavailable'),
        consumer: const CodexConsumerAccount(),
        apiKey: const CodexApiKeyState(state: 'unknown'),
        capabilities: const CodexCapabilities(),
        usableForCodex: false,
      );

  bool get chatGptSignedIn =>
      consumer.state == 'authenticated' && consumer.type == 'chatgpt';
  bool get apiKeyPresent => apiKey.state == 'present';

  CodexAccountPhase get phase {
    if (state == 'failed') return CodexAccountPhase.failed;
    if (state != 'ready') return CodexAccountPhase.unavailable;
    if (usableForCodex || chatGptSignedIn || apiKeyPresent) {
      return CodexAccountPhase.signedIn;
    }
    return CodexAccountPhase.signedOut;
  }

  String get primaryRouteLabel {
    if (phase == CodexAccountPhase.unavailable) {
      return 'Codex account unavailable';
    }
    if (effectiveAuthSource == 'api-key' || apiKeyPresent) {
      return 'OpenAI API billing route';
    }
    if (effectiveAuthSource == 'consumer-chatgpt' || chatGptSignedIn) {
      return 'ChatGPT subscription route';
    }
    return 'Sign-in needed';
  }

  String get chatGptLabel {
    if (!chatGptSignedIn) return 'ChatGPT account not signed in';
    final plan = _planLabel(consumer.planType);
    return plan.isEmpty
        ? 'ChatGPT account ready'
        : 'ChatGPT $plan account ready';
  }
}

class CodexConsumerAccount {
  final String state, type, planType;
  final bool emailPresent;
  const CodexConsumerAccount({
    this.state = 'unknown',
    this.type = '',
    this.planType = 'unknown',
    this.emailPresent = false,
  });

  factory CodexConsumerAccount.fromJson(Map<String, dynamic> json) =>
      CodexConsumerAccount(
        state: _text(json['state'], fallback: 'unknown'),
        type: _text(json['type']),
        planType: _text(json['plan_type'], fallback: 'unknown'),
        emailPresent: json['email_present'] == true,
      );
}

class CodexApiKeyState {
  final String state, source;
  const CodexApiKeyState({this.state = 'unknown', this.source = ''});
  factory CodexApiKeyState.fromJson(Map<String, dynamic> json) =>
      CodexApiKeyState(
        state: _text(json['state'], fallback: 'unknown'),
        source: _text(json['source']),
      );
}

class CodexCapabilities {
  final bool namespaceTools, imageGeneration, webSearch;
  const CodexCapabilities({
    this.namespaceTools = false,
    this.imageGeneration = false,
    this.webSearch = false,
  });
  factory CodexCapabilities.fromJson(Map<String, dynamic> json) =>
      CodexCapabilities(
        namespaceTools: json['namespace_tools'] == true,
        imageGeneration: json['image_generation'] == true,
        webSearch: json['web_search'] == true,
      );
}

class CodexLoginStart {
  final String state, mode, loginId, authUrl, verificationUrl, userCode, reason;
  const CodexLoginStart({
    required this.state,
    required this.mode,
    required this.loginId,
    required this.authUrl,
    required this.verificationUrl,
    required this.userCode,
    required this.reason,
  });

  factory CodexLoginStart.fromJson(Map<String, dynamic> json) =>
      CodexLoginStart(
        state: _text(json['state']),
        mode: _text(json['mode']),
        loginId: _text(json['login_id'] ?? json['loginId']),
        authUrl: _text(json['auth_url']),
        verificationUrl: _text(json['verification_url']),
        userCode: _text(json['user_code']),
        reason: _text(json['reason']),
      );

  Uri? get launchUri => trustedCodexLoginUrl(
        mode == 'device_code' ? verificationUrl : authUrl,
      );
}

class CodexLoginResult {
  final String state, loginId, completionState, reason;
  const CodexLoginResult({
    required this.state,
    required this.loginId,
    required this.completionState,
    required this.reason,
  });

  factory CodexLoginResult.fromJson(Map<String, dynamic> json) =>
      CodexLoginResult(
        state: _text(json['state']),
        loginId: _text(json['login_id'] ?? json['loginId']),
        completionState: _text(json['completion_state']),
        reason: _text(json['reason']),
      );

  bool get authenticated => state == 'authenticated';
  bool get pending => state == 'pending' || state == 'already_pending';
  bool get cancelled => state == 'cancelled' || state == 'canceled';
}

class CodexModelCatalog {
  final List<CodexModelRow> models;
  final String reason;
  final bool allowManual, listingAuthoritative;
  const CodexModelCatalog({
    required this.models,
    required this.reason,
    required this.allowManual,
    required this.listingAuthoritative,
  });
  factory CodexModelCatalog.empty({String reason = ''}) => CodexModelCatalog(
        models: const [],
        reason: reason,
        allowManual: false,
        listingAuthoritative: false,
      );
  factory CodexModelCatalog.fromJson(Map<String, dynamic> json) {
    final rawRows = json['models'];
    return CodexModelCatalog(
        models: rawRows is List
            ? [
                for (final row in rawRows)
                  if (row is Map) CodexModelRow.fromJson(_map(row)),
              ].where((row) => row.id.isNotEmpty).toList(growable: false)
            : const [],
        reason: _text(json['reason']),
        allowManual: json['allow_manual'] != false,
        listingAuthoritative: json['listing_authoritative'] == true);
  }
}

class CodexModelRow {
  final String id, displayName;
  final bool isDefault;
  const CodexModelRow({
    required this.id,
    required this.displayName,
    required this.isDefault,
  });
  factory CodexModelRow.fromJson(Map<String, dynamic> json) {
    final id = _text(json['id']);
    return CodexModelRow(
      id: id,
      displayName: _text(json['display_name'], fallback: id),
      isDefault: json['default'] == true || json['is_default'] == true,
    );
  }
}

Map<String, dynamic> _map(Object? value) {
  if (value is! Map) return const {};
  final mapped = <String, dynamic>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is String) mapped[key] = entry.value;
  }
  return mapped;
}

String _text(Object? value, {String fallback = ''}) {
  if (value is! String) return fallback;
  if (value.contains('\\')) return fallback;
  final cleaned = value
      .replaceAll(RegExp(r'[\x00-\x1F\x7F]'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  return cleaned.isEmpty ? fallback : cleaned;
}

String _planLabel(String value) {
  if (value.isEmpty || value == 'unknown') return '';
  return value
      .split(RegExp(r'[_-]+'))
      .map((part) => part.isEmpty
          ? ''
          : '${part[0].toUpperCase()}${part.substring(1).toLowerCase()}')
      .join(' ');
}
