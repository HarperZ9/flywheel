import 'package:flutter/material.dart';

import 'app.dart';
import 'services/settings.dart';

export 'app.dart' show FlywheelApp;

void main() => runApp(FlywheelApp(settings: DesktopSettings.load()));
