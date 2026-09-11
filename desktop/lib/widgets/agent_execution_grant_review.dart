import 'package:flutter/material.dart';

import '../models/gateway_grant_models.dart';
import '../theme/tokens.dart';

class AgentExecutionGrantReview extends StatelessWidget {
  final GatewayAgentExecutionReview review;
  const AgentExecutionGrantReview({super.key, required this.review});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).extension<FwTokens>() ?? FwTokens.light;
    return Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: t.panel,
          border: Border.all(color: t.line),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Agent execution',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          ..._children(context, t),
        ]),
      ),
    );
  }

  List<Widget> _children(BuildContext context, FwTokens t) {
    if (review.reprepareRequired) {
      return [
        _Line('Status', 'reprepare required', tokens: t),
        Text('This stored agent proposal needs a fresh review before use.',
            style: TextStyle(color: t.inkMuted, fontSize: 12.5)),
      ];
    }
    return [
      _Line('Requested model', review.model.requestedLabel, tokens: t),
      _Line('Resolved model', review.model.modelId, tokens: t),
      if (review.cliSession != null) ...[
        _Line('Execution mode', 'native CLI session', tokens: t),
        _Line('CLI engine', review.cliSession!.engineLabel, tokens: t),
        _Line('CLI profile', review.cliSession!.profile, tokens: t),
        _Line('CLI auth', review.cliSession!.authLabel, tokens: t),
      ],
      if (review.toolProtocol != null) ...[
        _Line('Tool protocol', review.toolProtocol!.protocolLabel, tokens: t),
        _Line('Tool schema digest', review.toolProtocol!.toolSchemaDigestLabel,
            tokens: t),
      ],
      _Line('Selection', review.model.selectionLabel, tokens: t),
      _Line('Observation basis', review.model.observationPolicyLabel,
          tokens: t),
      _Line('Endpoint', _endpointLabel, tokens: t),
      _Line('Workspace', review.root, tokens: t),
      _Line('Budget', review.budget.label, tokens: t),
      if (review.cliSession != null) ...[
        _Line('CLI bounds', review.cliSession!.boundsLabel, tokens: t),
        _Line('Filesystem scope', review.cliSession!.filesystemScopeLabel,
            tokens: t),
        _Line('Provider policy', review.cliSession!.providerPolicyLabel,
            tokens: t),
        _Line('Reasoning evidence', review.cliSession!.reasoningEvidenceLabel,
            tokens: t),
      ],
      _Line('Gates', review.capabilities.label, tokens: t),
      if (review.model.profile != null)
        _Line('Profile', review.model.profile!.profile, tokens: t),
      Material(
        type: MaterialType.transparency,
        child: Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: Text('Receipts and policy',
                style: TextStyle(
                    color: t.inkSoft,
                    fontWeight: FontWeight.w600,
                    fontSize: 13)),
            children: [
              _HashLine('Binding', review.bindingSha256, tokens: t),
              _HashLine('Workspace policy', review.workspacePolicySha256,
                  tokens: t),
              if (review.toolProtocol != null) ...[
                _ReceiptLine('Tool names', review.toolProtocol!.toolNamesLabel,
                    tokens: t),
                _ReceiptLine(
                    'Tool result order',
                    review.toolProtocol!.resultOrderPolicy.isEmpty
                        ? 'unknown'
                        : review.toolProtocol!.resultOrderPolicy,
                    tokens: t),
              ],
              if (review.cliSession != null) ...[
                _ReceiptLine('CLI tools', review.cliSession!.toolsLabel,
                    tokens: t),
                _ReceiptLine(
                    'CLI limitations', review.cliSession!.limitationsLabel,
                    tokens: t),
              ],
              if (review.model.profile != null) ...[
                _HashLine('Expected manifest',
                    review.model.profile!.expectedManifestSha256,
                    tokens: t),
                _HashLine('Expected artifact',
                    review.model.profile!.expectedArtifactSha256,
                    tokens: t),
              ],
            ],
          ),
        ),
      ),
    ];
  }

  String get _endpointLabel => review.baseUrl.isEmpty
      ? review.endpoint
      : '${review.endpoint} / ${review.baseUrl}';
}

class _Line extends StatelessWidget {
  final String label, value;
  final FwTokens tokens;
  const _Line(this.label, this.value, {required this.tokens});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text('$label: $value',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: tokens.inkSoft, fontSize: 13)),
      );
}

class _ReceiptLine extends StatelessWidget {
  final String label, value;
  final FwTokens tokens;
  const _ReceiptLine(this.label, this.value, {required this.tokens});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(children: [
          Text(label,
              style: TextStyle(
                  color: tokens.inkFaint,
                  fontFamily: tokens.monoFamily,
                  fontSize: 11.5)),
          const SizedBox(width: 8),
          Expanded(
              child: SelectableText(value,
                  maxLines: 2,
                  style: TextStyle(
                      color: tokens.inkSoft,
                      fontFamily: tokens.monoFamily,
                      fontSize: 12,
                      fontWeight: FontWeight.w600))),
        ]),
      );
}

class _HashLine extends StatelessWidget {
  final String label, hash;
  final FwTokens tokens;
  const _HashLine(this.label, this.hash, {required this.tokens});

  @override
  Widget build(BuildContext context) {
    final short = hash.length > 24 ? '${hash.substring(0, 24)}…' : hash;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(children: [
        Text(label,
            style: TextStyle(
                color: tokens.inkFaint,
                fontFamily: tokens.monoFamily,
                fontSize: 11.5)),
        const SizedBox(width: 8),
        Expanded(
            child: SelectableText(short,
                maxLines: 1,
                style: TextStyle(
                    color: tokens.inkSoft,
                    fontFamily: tokens.monoFamily,
                    fontSize: 12,
                    fontWeight: FontWeight.w600))),
      ]),
    );
  }
}
