import 'package:flutter/foundation.dart';

class UsageLiveSelection {
  final String endpoint, model;
  const UsageLiveSelection({String? endpoint, String? model})
      : endpoint = endpoint ?? '',
        model = model ?? '';

  static const none = UsageLiveSelection();

  bool get hasEndpoint => endpoint.trim().isNotEmpty;

  String get path {
    if (!hasEndpoint) return '/api/usage/live';
    final query = {
      'endpoint': endpoint.trim(),
      if (model.trim().isNotEmpty) 'model': model.trim(),
    };
    return Uri(path: '/api/usage/live', queryParameters: query).toString();
  }

  String get cacheKey => '${endpoint.trim()}|${model.trim()}';
}

class UsageLiveSelectionController extends ValueNotifier<UsageLiveSelection> {
  UsageLiveSelectionController() : super(UsageLiveSelection.none);
}
