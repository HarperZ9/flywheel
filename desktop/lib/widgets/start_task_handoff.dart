import 'package:flutter/foundation.dart';

@immutable
class StartTaskHandoff {
  final String text;
  const StartTaskHandoff(this.text);

  @override
  bool operator ==(Object other) =>
      other is StartTaskHandoff && other.text == text;

  @override
  int get hashCode => text.hashCode;
}
