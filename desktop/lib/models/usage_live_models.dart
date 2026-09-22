// Runtime observations are distinct from signed accounting receipts.
class UsageLiveSnapshot {
  final DateTime observedAt;
  final List<UsageLiveModel> models;
  const UsageLiveSnapshot(this.observedAt, this.models);

  factory UsageLiveSnapshot.fromJson(Map<String, dynamic> json) {
    final time = DateTime.tryParse('${json['observed_utc']}');
    if (json['schema'] != 'flywheel.usage-live/v1' ||
        time == null ||
        json['models'] is! List) {
      throw const FormatException('Invalid runtime observation');
    }
    final ids = <String>{};
    final models = <UsageLiveModel>[];
    for (final raw in (json['models'] as List).take(32)) {
      if (raw is! Map) continue;
      final model = UsageLiveModel.fromJson(raw);
      if (model.id.isNotEmpty && ids.add(model.id)) models.add(model);
    }
    return UsageLiveSnapshot(time.toUtc(), List.unmodifiable(models));
  }
}

class UsageLiveModel {
  final String id, model, endpoint, status, source;
  final String reason, counterScope;
  final double? intervalSeconds;
  final double? decode, prefill;
  final int? generated, prompt;
  const UsageLiveModel(
      {required this.id,
      required this.model,
      required this.endpoint,
      required this.status,
      required this.source,
      this.reason = '',
      this.counterScope = '',
      this.intervalSeconds,
      this.decode,
      this.prefill,
      this.generated,
      this.prompt});

  factory UsageLiveModel.fromJson(Map raw) {
    var status = switch (raw['status']) {
      'observed' => 'observed',
      'warming_up' => 'warming_up',
      _ => 'unavailable',
    };
    final decode =
        status == 'observed' ? _rate(raw['decode_tokens_per_second']) : null;
    final prefill =
        status == 'observed' ? _rate(raw['prefill_tokens_per_second']) : null;
    if (status == 'observed' && decode == null && prefill == null) {
      status = 'unavailable';
    }
    final denominator = raw['report_denominator'];
    final interval = denominator is Map ? _rate(denominator['seconds']) : null;
    return UsageLiveModel(
      id: _text(raw['id']),
      model: _text(raw['model']),
      endpoint: _text(raw['endpoint']),
      status: status,
      source: _text(raw['source']),
      reason: _text(raw['reason']),
      counterScope: _text(raw['counter_scope']),
      intervalSeconds: interval != null && interval > 0 ? interval : null,
      decode: decode,
      prefill: prefill,
      generated: _count(raw['generated_tokens']),
      prompt: _count(raw['prompt_tokens']),
    );
  }

  static double? _rate(dynamic v) =>
      v is num && v.isFinite && v >= 0 ? v.toDouble() : null;
  static int? _count(dynamic v) => v is int && v >= 0 ? v : null;
  static String _text(dynamic v) {
    if (v is! String || v.contains(RegExp(r'[\x00-\x1f\x7f]'))) return '';
    return v.length <= 160 ? v : '${v.substring(0, 157)}…';
  }
}

class UsageRatePoint {
  final DateTime time;
  final double? decode, prefill;
  const UsageRatePoint(this.time, this.decode, this.prefill);
}

String usageCount(int? value) => value == null
    ? 'Not reported'
    : value
        .toString()
        .replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+(?!\d))'), (m) => '${m[1]},');
String usageRate(double? value) =>
    value == null ? 'Not reported' : '${value.toStringAsFixed(1)} tok/s';
