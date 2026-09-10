part of 'gateway_grant_summary.dart';

bool isCanonicalBulletinOrigin(String value) {
  return _canonicalBulletinOrigin(value) == value;
}

String? _canonicalBulletinOrigin(String value) {
  if (value.isEmpty ||
      value.length > 300 ||
      value.contains('\\') ||
      value.contains('%') ||
      value.contains('?') ||
      value.contains('#') ||
      value.contains('@') ||
      value.codeUnits.any(
        (unit) => unit > 0x7f || unit <= 0x20 || unit == 0x7f,
      )) {
    return null;
  }
  try {
    final uri = Uri.parse(value);
    final scheme = uri.scheme;
    if (!uri.hasAuthority ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        !(uri.path.isEmpty || uri.path == '/') ||
        uri.authority.endsWith(':')) {
      return null;
    }
    final host = _canonicalBulletinHost(uri.host, uri.authority);
    if (host == null) return null;
    final port = uri.hasPort ? uri.port : null;
    if (port != null && (port < 1 || port > 65535)) return null;
    if (scheme == 'https') {
      // All canonical HTTPS hostnames, IPv4 literals, and IPv6 literals are
      // accepted. Loopback authorization is a runtime policy, not a syntax
      // restriction in the operation contract.
    } else if (scheme == 'http') {
      if (!_httpLoopbackOrigins.contains(host)) return null;
    } else {
      return null;
    }
    final defaultPort = scheme == 'https' ? 443 : 80;
    final portText = port == null || port == defaultPort ? '' : ':$port';
    return '$scheme://$host$portText';
  } on Object {
    return null;
  }
}

const _httpLoopbackOrigins = {'127.0.0.1', 'localhost', '[::1]'};
final _bulletinHostLabel = RegExp(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$');

String? _canonicalBulletinHost(String host, String authority) {
  if (host.isEmpty) return null;
  if (authority.startsWith('[') && !host.contains(':')) return null;
  if (host.contains(':')) {
    final address = InternetAddress.tryParse(host);
    if (address == null ||
        address.type != InternetAddressType.IPv6 ||
        address.rawAddress.length != 16) {
      return null;
    }
    return '[${_compressedIpv6(address.rawAddress)}]';
  }
  if (host.length > 253) return null;
  for (final label in host.split('.')) {
    if (!_bulletinHostLabel.hasMatch(label)) return null;
  }
  return host;
}

String _compressedIpv6(List<int> bytes) {
  final groups = List<int>.generate(
    8,
    (index) => bytes[index * 2] << 8 | bytes[index * 2 + 1],
  );
  var bestStart = -1;
  var bestLength = 0;
  var index = 0;
  while (index < groups.length) {
    if (groups[index] != 0) {
      index++;
      continue;
    }
    final start = index;
    while (index < groups.length && groups[index] == 0) {
      index++;
    }
    final length = index - start;
    if (length >= 2 && length > bestLength) {
      bestStart = start;
      bestLength = length;
    }
  }
  if (bestStart == -1) {
    return groups.map((group) => group.toRadixString(16)).join(':');
  }
  final before = groups
      .take(bestStart)
      .map((group) => group.toRadixString(16))
      .toList();
  final after = groups
      .skip(bestStart + bestLength)
      .map((group) => group.toRadixString(16))
      .toList();
  if (before.isEmpty && after.isEmpty) return '::';
  if (before.isEmpty) return '::${after.join(':')}';
  if (after.isEmpty) return '${before.join(':')}::';
  return '${before.join(':')}::${after.join(':')}';
}

final class GatewayDestination {
  final String kind, ref;
  final String? bulletinBaseUrl;
  const GatewayDestination(this.kind, this.ref, [this.bulletinBaseUrl]);

  factory GatewayDestination.fromJson(
    Object? raw,
    List<ParseIssue> issues,
    String field,
  ) {
    const baseFields = {'kind', 'ref'};
    const bulletinFields = {'kind', 'ref', 'bulletin_base_url'};
    if (raw is! Map<String, Object?>) {
      addParseIssue(issues, field, raw);
      return const GatewayDestination('', '');
    }
    final keys = raw.keys.toSet();
    if (!keys.containsAll(baseFields) ||
        !(keys.length == baseFields.length ||
            keys.difference(bulletinFields).isEmpty)) {
      addParseIssue(issues, field, raw);
      return const GatewayDestination('', '');
    }
    final kind = readText(raw, 'kind', issues);
    final ref = raw['ref'];
    final bulletinBaseUrl = _readDestinationBulletinOrigin(
      raw,
      kind,
      ref is String ? ref : '',
      issues,
      field,
    );
    if (pathDestinationKinds.contains(kind) &&
        ref is String &&
        ref.isNotEmpty &&
        isSafeLocalPath(ref)) {
      return GatewayDestination(kind, ref);
    }
    return GatewayDestination(
      kind,
      readText(raw, 'ref', issues),
      bulletinBaseUrl,
    );
  }

  Map<String, String> toJson() => {
    'kind': kind,
    'ref': ref,
    if (bulletinBaseUrl != null) 'bulletin_base_url': bulletinBaseUrl!,
  };

  @override
  bool operator ==(Object other) =>
      other is GatewayDestination &&
      kind == other.kind &&
      ref == other.ref &&
      bulletinBaseUrl == other.bulletinBaseUrl;

  @override
  int get hashCode => Object.hash(kind, ref, bulletinBaseUrl);
}

String? _readDestinationBulletinOrigin(
  Map<String, Object?> raw,
  String kind,
  String ref,
  List<ParseIssue> issues,
  String field,
) {
  if (!raw.containsKey('bulletin_base_url')) return null;
  final value = raw['bulletin_base_url'];
  if (kind != 'lane' ||
      ref != 'bulletin' ||
      value is! String ||
      !isCanonicalBulletinOrigin(value)) {
    addParseIssue(issues, '$field.bulletin_base_url', value);
    return null;
  }
  return value;
}
