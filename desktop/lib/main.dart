import 'package:flutter/material.dart';

import 'app.dart';
import 'client/gateway_auth.dart' show initFlywheelHome;
import 'services/settings.dart';

export 'app.dart' show FlywheelApp;

Future<void> main() async {
  // path_provider needs the platform channel, and the mobile home must resolve
  // before the first store loads, so the paired connection, chat history, and
  // settings all read from the writable app-private directory.
  WidgetsFlutterBinding.ensureInitialized();
  await initFlywheelHome();
  runApp(FlywheelApp(settings: DesktopSettings.load()));
}
