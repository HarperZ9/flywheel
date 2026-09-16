final _chatWindowsPath = RegExp(r'(?:^|[\s=(\[{,:;])[A-Za-z]:[\\/]');
final _chatUncPath =
    RegExp(r'(?:^|[\s=(\[{,;])(?:\\\\|//)[^\\/\s]+[\\/][^\s]+');
final _chatPrivatePath = RegExp(r'(?:^|[\s=(\[{,:;])/(?!/)[^\s]+');
final _chatFileUri = RegExp(r'(?<![A-Za-z0-9+.-])file:', caseSensitive: false);
final _chatSecretValue = RegExp(
    r'(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-(?:live|proj|ant)[A-Za-z0-9_-]{10,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b)');
final _chatAssignedSecret = RegExp(
    r'\b(?:secret|password|passwd|api_key|access_key|token|credential)\s*[:=]\s*["\x27]?[A-Za-z0-9/+_-]{12,}',
    caseSensitive: false);
final _chatSecretKey = RegExp(r'^(?:api_keys?|access_tokens?|refresh_tokens?|'
    r'tokens?|passwords?|secrets?|credentials?|private_keys?|authorizations?|'
    r'cookies?|environments?|envs?|passwds?|access_keys?|.+_(?:api_keys?|'
    r'private_keys?|passwords?|secrets?|credentials?|tokens?))$');

const _chatPercentDecodeLimit = 4;

bool safeChatLocalText(String value) {
  try {
    for (final form in _chatPercentForms(value)) {
      if (!_safeChatForm(form)) return false;
    }
    return true;
  } catch (_) {
    return false;
  }
}

bool _safeChatForm(String value) =>
    !_chatWindowsPath.hasMatch(value) &&
    !_chatUncPath.hasMatch(value) &&
    !_chatPrivatePath.hasMatch(value) &&
    !_chatFileUri.hasMatch(value) &&
    !_chatSecretValue.hasMatch(value) &&
    !_chatAssignedSecret.hasMatch(value);

bool isChatLocalSecretKey(String key) {
  try {
    return _chatPercentForms(key).any((form) =>
        _chatSecretKey.hasMatch(form.toLowerCase().replaceAll('-', '_')));
  } catch (_) {
    return true;
  }
}

bool safeChatLocalRef(String value) =>
    value.isNotEmpty && value.length <= 256 && !value.contains(':');

String _decodeChatPercent(String value) {
  final result = StringBuffer();
  for (var index = 0; index < value.length;) {
    if (value.codeUnitAt(index) != 0x25) {
      result.writeCharCode(value.codeUnitAt(index++));
      continue;
    }
    final next = index + 1 < value.length ? value.codeUnitAt(index + 1) : null;
    if (index + 2 >= value.length ||
        !_chatHex(next) ||
        !_chatHex(value.codeUnitAt(index + 2))) {
      result.write('%');
      index++;
      continue;
    }
    final start = index;
    while (index + 2 < value.length &&
        value.codeUnitAt(index) == 0x25 &&
        _chatHex(value.codeUnitAt(index + 1)) &&
        _chatHex(value.codeUnitAt(index + 2))) {
      index += 3;
    }
    try {
      result.write(Uri.decodeComponent(value.substring(start, index)));
    } catch (_) {
      throw ArgumentError('Invalid encoded local text');
    }
  }
  return result.toString();
}

Iterable<String> _chatPercentForms(String value) sync* {
  var current = value;
  for (var depth = 0; depth <= _chatPercentDecodeLimit; depth++) {
    yield current;
    final decoded = _decodeChatPercent(current);
    if (decoded == current) return;
    current = decoded;
  }
  throw ArgumentError('Encoded local text did not stabilize');
}

bool _chatHex(int? value) =>
    value != null &&
    ((value >= 0x30 && value <= 0x39) ||
        (value >= 0x41 && value <= 0x46) ||
        (value >= 0x61 && value <= 0x66));
