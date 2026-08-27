// Falsifiers for the pairing panel: a user pairs a gateway (URL + token) from
// inside the app, no config file, and the choice persists through the store.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/services/connection_config.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/connection_panel.dart';

void main() {
  Widget host(ConnectionStore store) => MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: ConnectionForm(store: store)),
      );

  ConnectionStore tempStore() {
    final dir = Directory.systemTemp.createTempSync('conn-panel-');
    return ConnectionStore(file: File('${dir.path}/connection.json'));
  }

  testWidgets('pairing a gateway persists the url and token', (tester) async {
    final store = tempStore();
    await tester.pumpWidget(host(store));

    await tester.enterText(
        find.byKey(const Key('connection-url')), 'https://pc.example');
    await tester.enterText(
        find.byKey(const Key('connection-token')), 'tok-xyz');
    await tester.tap(find.text('Pair'));
    await tester.pump();

    final saved = store.load();
    expect(saved.baseUrl, 'https://pc.example');
    expect(saved.token, 'tok-xyz');
    expect(saved.isRemote, isTrue);
  });

  testWidgets('use local engine clears the pairing', (tester) async {
    final store = tempStore()
      ..save(const ConnectionConfig(baseUrl: 'https://x', token: 't'));
    await tester.pumpWidget(host(store));

    await tester.tap(find.text('Use local engine'));
    await tester.pump();

    expect(store.load().isRemote, isFalse);
  });

  testWidgets('the form shows the existing pairing on open', (tester) async {
    final store = tempStore()
      ..save(const ConnectionConfig(baseUrl: 'https://loaded.example', token: 's'));
    await tester.pumpWidget(host(store));

    expect(find.text('https://loaded.example'), findsOneWidget);
  });
}
