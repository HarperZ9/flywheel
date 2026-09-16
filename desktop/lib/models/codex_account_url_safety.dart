// Defensive URL trust checks for Codex consumer-account login handoff.

final _secretPatterns = [
  RegExp(r'sk-[A-Za-z0-9_-]{8,}', caseSensitive: false),
  RegExp(r'Bearer\s+[A-Za-z0-9._-]{8,}', caseSensitive: false),
  RegExp(r'(access|refresh|id)[_-]?token=[^&\s]+', caseSensitive: false),
];

const _forbiddenQueryNames = [
  'token',
  'secret',
  'password',
  'credential',
  'api_key',
];

Uri? trustedCodexLoginUrl(String raw) {
  if (raw.isEmpty || raw.contains('\\') || raw.contains(RegExp(r'\s'))) {
    return null;
  }
  if (_secretShaped(raw)) return null;
  final uri = Uri.tryParse(raw);
  if (uri == null || uri.scheme != 'https' || uri.userInfo.isNotEmpty) {
    return null;
  }
  if (!_hostAllowed(uri.host)) return null;
  if (_queryNameForbidden(uri.query)) return null;
  if (_decodedPartsUnsafe(uri)) return null;
  return uri;
}

bool _hostAllowed(String rawHost) {
  final host = rawHost.toLowerCase().replaceFirst(RegExp(r'\.$'), '');
  return host == 'openai.com' ||
      host.endsWith('.openai.com') ||
      host == 'chatgpt.com' ||
      host.endsWith('.chatgpt.com');
}

bool _queryNameForbidden(String query) {
  final lowerQuery = query.toLowerCase();
  if (_forbiddenQueryNames.any(lowerQuery.contains)) return true;
  try {
    final params = Uri.splitQueryString(query);
    for (final key in params.keys) {
      final lower = key.toLowerCase();
      if (_forbiddenQueryNames.any(lower.contains)) return true;
    }
  } on FormatException {
    return true;
  }
  return false;
}

bool _decodedPartsUnsafe(Uri uri) {
  try {
    final decodedQuery = Uri.decodeQueryComponent(uri.query);
    final decodedFragment = Uri.decodeComponent(uri.fragment);
    if (_secretShaped(decodedQuery) || _secretShaped(decodedFragment)) {
      return true;
    }
    for (final values in uri.queryParametersAll.values) {
      for (final value in values) {
        if (_secretShaped(value)) return true;
      }
    }
    return false;
  } on FormatException {
    return true;
  }
}

bool _secretShaped(String value) =>
    _secretPatterns.any((pattern) => pattern.hasMatch(value));
