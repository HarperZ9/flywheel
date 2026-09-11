import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

import 'gateway_agent_execution_review_fixtures.dart';

Map<String, Object?> _reviewFixture(String name) =>
    (jsonDecode(File('test/fixtures/native_cli_session/$name-review.json')
            .readAsStringSync()) as Map)
        .cast<String, Object?>();

Map<String, Object?> _without(Map<String, Object?> source, String key) =>
    Map<String, Object?>.from(source)..remove(key);

void main() {
  test('agent execution summary accepts frozen Claude v3 CLI review fixtures',
      () {
    final cases = {
      'claude-read': (
        hash:
            '21d35b0a0fb3dfa7ca9fd60c6fcfadd254b1c0ebf04970ec76d45340c01ca9ce',
        provider: 'claude-cli',
        profile: 'claude_restricted_files_v1',
        tools: ['Read', 'Glob', 'Grep'],
        maxStepsControl: 'native_turn_limit',
        scope: 'working_directory_file_tools',
        allowWrite: false,
        allowExec: false,
      ),
      'claude-write': (
        hash:
            'c02b08fc38ef9cb92a7f3fed80b2cd8044d49eb4311abdc84c0d114da1ae23e1',
        provider: 'claude-cli',
        profile: 'claude_restricted_files_v1',
        tools: ['Read', 'Glob', 'Grep', 'Edit', 'Write'],
        maxStepsControl: 'native_turn_limit',
        scope: 'working_directory_file_tools',
        allowWrite: true,
        allowExec: false,
      ),
    };

    for (final entry in cases.entries) {
      final parsed = GatewayGrantProposal.fromJson(
          gatewayAgentProposal(agentExecution: _reviewFixture(entry.key)));

      expect(parsed.invalidResponse, isFalse, reason: entry.key);
      final review = parsed.summary.agentExecution!;
      expect(review.bindingSha256, entry.value.hash, reason: entry.key);
      expect(review.executionMode, 'native_cli_session', reason: entry.key);
      expect(review.endpoint, entry.value.provider, reason: entry.key);
      expect(review.baseUrl, isEmpty, reason: entry.key);
      expect(review.budget.maxSteps, 4, reason: entry.key);
      expect(review.budget.maxTokens, isNull, reason: entry.key);
      expect(review.budget.label, '4 steps / output tokens unsupported / 60s',
          reason: entry.key);
      expect(review.capabilities.allowWrite, entry.value.allowWrite,
          reason: entry.key);
      expect(review.capabilities.allowExec, entry.value.allowExec,
          reason: entry.key);
      expect(review.cliSession?.provider, entry.value.provider,
          reason: entry.key);
      expect(review.cliSession?.profile, entry.value.profile,
          reason: entry.key);
      expect(review.cliSession?.tools, entry.value.tools, reason: entry.key);
      expect(review.cliSession?.filesystemScope, entry.value.scope,
          reason: entry.key);
      expect(review.cliSession?.authMode, 'official_cli_own_auth',
          reason: entry.key);
      expect(review.cliSession?.controls.maxSteps, entry.value.maxStepsControl,
          reason: entry.key);
      expect(review.cliSession?.controls.maxTokens, 'unsupported',
          reason: entry.key);
      expect(
          review.cliSession?.limitations,
          containsAll([
            'PROVIDER_POLICY_APPLIES',
            'NO_HARD_TOKEN_LIMIT',
            'HIDDEN_REASONING_UNAVAILABLE',
            'CLAUDE_REASONING_NOT_RETAINED'
          ]),
          reason: entry.key);
    }
  });

  test('agent v3 native CLI review rejects malformed or unknown authority', () {
    expect(
        GatewayGrantProposal.fromJson(gatewayAgentProposal(
                agentExecution: _reviewFixture('codex-read')))
            .invalidResponse,
        isTrue,
        reason: 'Codex CLI v3 fixture is pending backend admission repair');
    expect(
        GatewayGrantProposal.fromJson(gatewayAgentProposal(
                agentExecution: _reviewFixture('codex-write')))
            .invalidResponse,
        isTrue,
        reason: 'Codex CLI v3 fixture is pending backend admission repair');

    final review = _reviewFixture('claude-write');
    final session = review['cli_session'] as Map<String, Object?>;
    final controls = session['controls'] as Map<String, Object?>;
    final budget = review['budget'] as Map<String, Object?>;

    var caseIndex = 0;
    for (final bad in <Map<String, Object?>>[
      {...review, 'extra': 'field'},
      {...review, 'schema': 'flywheel.gateway-agent-review/v2'},
      _without(review, 'execution_mode'),
      _without(review, 'cli_session'),
      {...review, 'execution_mode': 'api_native_tools'},
      {...review, 'base_url': 'https://api.openai.com/v1'},
      {
        ...review,
        'budget': {...budget, 'max_tokens': 4096},
      },
      {
        ...review,
        'cli_session': {...session, 'extra': 'field'},
      },
      {
        ...review,
        'cli_session': {...session, 'provider': 'codex-cli'},
      },
      {
        ...review,
        'cli_session': {...session, 'profile': 'claude_unrestricted_v1'},
      },
      {
        ...review,
        'cli_session': {
          ...session,
          'tools': ['Edit', 'Read', 'Write']
        },
      },
      {
        ...review,
        'cli_session': {...session, 'auth_mode': 'api_key_injected'},
      },
      {
        ...review,
        'cli_session': {
          ...session,
          'controls': {...controls, 'max_tokens': 'native_limit'},
        },
      },
      {
        ...review,
        'cli_session': {
          ...session,
          'limitations': ['NO_HARD_TOKEN_LIMIT'],
        },
      },
    ]) {
      expect(
          GatewayGrantProposal.fromJson(
                  gatewayAgentProposal(agentExecution: bad))
              .invalidResponse,
          isTrue,
          reason: 'malformed case ${caseIndex++}');
    }
  });

  testWidgets('agent grant sheet renders native CLI v3 limits truthfully',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 1100));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = await preparedAgentGrantController(
        agentExecution: _reviewFixture('claude-write'));
    await openGatewayGrantSheet(tester, controller);

    expect(find.text('Agent execution'), findsOneWidget);
    expect(find.textContaining('Resolved model: fixture-model-exact'),
        findsOneWidget);
    expect(find.textContaining('Execution mode: native CLI session'),
        findsOneWidget);
    expect(find.textContaining('CLI engine: claude-cli / 2.1.251'),
        findsOneWidget);
    expect(find.textContaining('CLI auth: official CLI owns authentication'),
        findsOneWidget);
    expect(
        find.textContaining(
            'Budget: 4 steps / output tokens unsupported / 60s'),
        findsOneWidget);
    expect(
        find.textContaining(
            'CLI bounds: process deadline; steps native turn limit; tokens unsupported; seed unsupported'),
        findsOneWidget);
    expect(
        find.textContaining('Filesystem scope: working directory file tools'),
        findsOneWidget);
    expect(
        find.textContaining(
            'Provider policy: provider policy applies; hooks may be provider-managed'),
        findsOneWidget);
    expect(
        find.textContaining(
            'Reasoning evidence: hidden reasoning unavailable; Claude reasoning not retained'),
        findsOneWidget);
    expect(find.textContaining('Gates: write on / exec off / MCP off'),
        findsOneWidget);

    await tester.ensureVisible(find.text('Receipts and policy'));
    await tester.tap(find.text('Receipts and policy'));
    await tester.pumpAndSettle();

    expect(find.text('CLI tools'), findsOneWidget);
    expect(
        find.textContaining('Read, Glob, Grep, Edit, Write'), findsOneWidget);
    expect(find.text('CLI limitations'), findsOneWidget);
    expect(find.textContaining('NO_HARD_TOKEN_LIMIT'), findsOneWidget);
  });
}
