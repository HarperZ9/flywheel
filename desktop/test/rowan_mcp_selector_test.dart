import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/rowan_operation_card.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _receipt =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _selection = {
  'schema': 'flywheel.agent-run-mcp-admission-request/v1',
  'servers': [
    {
      'server_id': 'index',
      'catalog_ref': 'index',
      'receipt_sha256': _receipt,
      'tools': ['index.doctor'],
      'timeout_s': 10,
    },
  ],
};

Map<String, Object?> _catalog() => {
      'schema': 'flywheel.agent-mcp-catalog/v1',
      'servers': [
        _server('index', 'index.doctor'),
        _server('forum', 'forum.search'),
      ],
    };

Map<String, Object?> _server(String id, String tool) => {
      'server_id': id,
      'catalog_ref': id,
      'availability': {'status': 'available'},
      'tools': [
        {
          'source_tool_name': tool,
          'declared_authority': {
            'read': true,
            'write': false,
            'execute': false,
            'critical': false,
            'network': false,
          },
          'authority_source': 'gateway_catalog_metadata:v1',
          'does_not_prove': ['metadata does not sandbox code'],
        },
      ],
    };

Map<String, Object?> _discovery(Map<String, Object?> admission) => {
      'schema': 'flywheel.agent-mcp-discovery-response/v1',
      'mcp_admission': admission,
      'receipt': {
        'server_id': ((admission['servers'] as List).first
            as Map<String, Object?>)['server_id'],
        'catalog_ref': ((admission['servers'] as List).first
            as Map<String, Object?>)['catalog_ref'],
        'receipt_sha256': ((admission['servers'] as List).first
            as Map<String, Object?>)['receipt_sha256'],
        'expires_at_unix': 1800000000,
        'selected_tools': ((admission['servers'] as List).first
            as Map<String, Object?>)['tools'],
      },
    };

Future<BuildContext> _mount(
  WidgetTester tester,
  GatewayOperationAuthorizer authorize,
) async {
  late BuildContext context;
  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: GatewayOperationScope(
      authorize: authorize,
      child: Builder(builder: (ctx) {
        context = ctx;
        return const SizedBox.shrink();
      }),
    ),
  ));
  return context;
}

void main() {
  testWidgets('Rowan MCP selector loads catalog and stores receipt selection',
      (tester) async {
    Map<String, dynamic>? discoveryRequest;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent/mcp/catalog') {
          return http.Response(jsonEncode(_catalog()), 200);
        }
        if (request.url.path == '/api/agent/mcp/discovery-receipts') {
          expect(request.followRedirects, isFalse);
          discoveryRequest = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(_discovery(_selection)), 200);
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client)..setEndpoint('openai');
    addTearDown(() {
      rowan.dispose();
      client.close();
    });
    final root = TextEditingController(text: r'C:\fixture\workspace');
    final tokens = TextEditingController(text: '1024');
    final timeout = TextEditingController(text: '300');
    addTearDown(root.dispose);
    addTearDown(tokens.dispose);
    addTearDown(timeout.dispose);

    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
          body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: rowan,
          builder: (context, _) => RowanOperationCard(
            rowan: rowan,
            root: root,
            tokens: tokens,
            timeout: timeout,
            onRun: () {},
          ),
        ),
      )),
    ));

    await tester.tap(find.byKey(const Key('assistant-rowan-mcp-refresh')));
    await tester.pumpAndSettle();
    expect(find.text('index / index.doctor'), findsOneWidget);

    await tester.tap(find.byKey(const Key('assistant-rowan-mcp-admit')));
    await tester.pumpAndSettle();

    expect(rowan.mcpAdmission, _selection);
    expect(discoveryRequest, isNotNull);
    expect(
        discoveryRequest!['schema'], 'flywheel.agent-mcp-discovery-request/v1');
    expect(discoveryRequest!['catalog_ref'], 'index');
    expect(discoveryRequest!['server_id'], 'index');
    expect(discoveryRequest!['tools'], ['index.doctor']);
    expect(discoveryRequest!['timeout_s'], 10);
    expect(discoveryRequest!['discovery_authorization'], {
      'reason': 'Rowan MCP selector requested index / index.doctor',
      'timeout_s': 10,
      'network': false,
    });
    expect(rowan.toolProtocol.wire, 'native');
  });

  testWidgets('changing MCP option clears old admission before Rowan start',
      (tester) async {
    Map<String, Object?>? prepared;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent/mcp/catalog') {
          return http.Response(jsonEncode(_catalog()), 200);
        }
        if (request.url.path == '/api/agent/mcp/discovery-receipts') {
          return http.Response(jsonEncode(_discovery(_selection)), 200);
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client)..setEndpoint('openai');
    addTearDown(() {
      rowan.dispose();
      client.close();
    });

    await rowan.loadMcpCatalog();
    await rowan.admitSelectedMcpTool();
    expect(rowan.mcpAdmission, _selection);

    rowan.selectMcpOption(rowan.mcpOptions[1].key);
    final context = await _mount(tester, (_, operation, __, ___) async {
      prepared = Map<String, Object?>.from(operation.operation);
      return const GatewayAuthorizationOutcome.denied();
    });

    final outcome = await rowan.start(context, 'inspect with changed MCP');

    expect(outcome.denied, isTrue);
    expect(rowan.selectedMcpOption?.label, 'forum / forum.search');
    expect(rowan.toolProtocol.wire, 'native');
    expect(rowan.mcpAdmission, isNull);
    expect(prepared!.containsKey('mcp_admission'), isFalse);
  });

  test('failed MCP rediscovery clears prior admission', () async {
    var failDiscovery = false;
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent/mcp/catalog') {
          return http.Response(jsonEncode(_catalog()), 200);
        }
        if (request.url.path == '/api/agent/mcp/discovery-receipts') {
          if (failDiscovery) {
            return http.Response('discovery failed', 500);
          }
          return http.Response(jsonEncode(_discovery(_selection)), 200);
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client)..setEndpoint('openai');
    addTearDown(() {
      rowan.dispose();
      client.close();
    });

    await rowan.loadMcpCatalog();
    await rowan.admitSelectedMcpTool();
    expect(rowan.mcpAdmission, _selection);

    rowan.selectMcpOption(rowan.mcpOptions[1].key);
    failDiscovery = true;
    await rowan.admitSelectedMcpTool();

    expect(rowan.error, isNotNull);
    expect(rowan.selectedMcpOption?.label, 'forum / forum.search');
    expect(rowan.mcpAdmission, isNull);
  });

  test('late MCP discovery cannot restore a stale option admission', () async {
    final firstDiscovery = Completer<http.Response>();
    final client = GatewayClient(
      baseUrl: 'https://rowan.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/agent/mcp/catalog') {
          return http.Response(jsonEncode(_catalog()), 200);
        }
        if (request.url.path == '/api/agent/mcp/discovery-receipts') {
          return firstDiscovery.future;
        }
        return http.Response('{}', 404);
      }),
    );
    final rowan = RowanOperationController(client)..setEndpoint('openai');
    addTearDown(() {
      rowan.dispose();
      client.close();
    });

    await rowan.loadMcpCatalog();
    final pending = rowan.admitSelectedMcpTool();
    await Future<void>.delayed(Duration.zero);

    rowan.selectMcpOption(rowan.mcpOptions[1].key);
    firstDiscovery.complete(
      http.Response(jsonEncode(_discovery(_selection)), 200),
    );
    await pending;

    expect(rowan.selectedMcpOption?.label, 'forum / forum.search');
    expect(rowan.mcpDiscoveryRunning, isFalse);
    expect(rowan.mcpAdmission, isNull);
  });
}
