import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/approval_inbox_api.dart';
import '../client/gateway_client.dart';
import '../controllers/approval_inbox_controller.dart';
import '../models/approval_inbox_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';

class ApprovalsInboxView extends StatefulWidget {
  final ApprovalInboxApi? api;
  final GatewayClient? client;
  final bool alive;

  const ApprovalsInboxView({
    super.key,
    this.api,
    this.client,
    required this.alive,
  }) : assert(api != null || client != null);

  @override
  State<ApprovalsInboxView> createState() => _ApprovalsInboxViewState();
}

class _ApprovalsInboxViewState extends State<ApprovalsInboxView> {
  late final ApprovalInboxController _controller;

  @override
  void initState() {
    super.initState();
    _controller = ApprovalInboxController(
        api: widget.api ?? GatewayApprovalInboxApi(widget.client!),
        alive: widget.alive);
    unawaited(_controller.refresh());
  }

  @override
  void didUpdateWidget(covariant ApprovalsInboxView oldWidget) {
    super.didUpdateWidget(oldWidget);
    _controller.setAlive(widget.alive);
    if (!oldWidget.alive && widget.alive) unawaited(_controller.refresh());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
      animation: _controller,
      builder: (context, _) => ViewScroll(
            storageKey: 'approvals-inbox',
            children: [
              SectionHeader('Approvals / Active Work',
                  kicker: 'mobile approval',
                  trailing: OutlinedButton(
                      onPressed: _controller.phase == ApprovalInboxPhase.loading
                          ? null
                          : () => unawaited(_controller.refresh()),
                      child: const Text('Refresh'))),
              const SizedBox(height: FwLayout.s3),
              if (_controller.message != null) ...[
                HonestNull(_controller.message!),
                const SizedBox(height: FwLayout.s4),
              ],
              if (_controller.phase == ApprovalInboxPhase.loading ||
                  _controller.phase == ApprovalInboxPhase.acting) ...[
                const LinearProgressIndicator(minHeight: 2),
                const SizedBox(height: FwLayout.s4),
              ],
              _pendingSection(context),
              const SizedBox(height: FwLayout.s5),
              _reviewSection(context),
              const SizedBox(height: FwLayout.s5),
              _activeWorkSection(context),
            ],
          ));

  Widget _pendingSection(BuildContext context) {
    final items = _controller.items;
    final completeness = _controller.listCompletenessMessage;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('pending approvals'),
      const SizedBox(height: FwLayout.s2),
      if (_controller.phase == ApprovalInboxPhase.upgradeRequired)
        const HonestNull('Install a gateway build with reviewed approval, '
            'proposal list/read, and durable reject.'),
      if (_controller.phase != ApprovalInboxPhase.upgradeRequired &&
          completeness != null)
        HonestNull(completeness),
      if (_controller.phase != ApprovalInboxPhase.upgradeRequired &&
          completeness == null &&
          items.isEmpty)
        const HonestNull('No indexed pending proposals.'),
      for (final item in items) ...[
        const SizedBox(height: FwLayout.s2),
        _ProposalRow(
          item: item,
          selected: item.proposalRef == _controller.selectedItem?.proposalRef,
          onTap: () => unawaited(_controller.open(item)),
        ),
      ],
      if (_controller.canLoadMore || _controller.loadingMore) ...[
        const SizedBox(height: FwLayout.s3),
        OutlinedButton(
            onPressed: _controller.loadingMore
                ? null
                : () => unawaited(_controller.loadMore()),
            child: Text(
                _controller.loadingMore ? 'Loading more...' : 'Load more')),
      ],
    ]);
  }

  Widget _reviewSection(BuildContext context) {
    final read = _controller.selectedRead;
    final item = _controller.selectedItem;
    if (item == null) return const SizedBox.shrink();
    final review = read?.review;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SectionHeader('Exact operation review', kicker: 'read before approve'),
        const SizedBox(height: FwLayout.s3),
        _Facts(item: item, review: review),
        const SizedBox(height: FwLayout.s3),
        const HonestNull('Open Relay or Journey active work view to cancel a '
            'running operation. Pending approvals can only be approved, '
            'rejected, or dismissed here.'),
        if (read != null && !read.reviewAvailable) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull('Review unavailable: ${read.unavailableReason}'),
        ],
        const SizedBox(height: FwLayout.s4),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          TextButton(
              onPressed: _controller.dismissSelected,
              child: const Text('Dismiss')),
          OutlinedButton(
              onPressed: _controller.canReject
                  ? () => unawaited(_controller.rejectSelected())
                  : null,
              child: const Text('Reject')),
          if (_controller.canApprove)
            FilledButton(
                onPressed: () => unawaited(_controller.approveSelected()),
                child: const Text('Approve reviewed')),
        ]),
        if (review != null) ...[
          const SizedBox(height: FwLayout.s3),
          _ExactJsonBlock(review: review),
        ],
      ]),
    );
  }

  Widget _activeWorkSection(BuildContext context) {
    final snapshot = _controller.activeWork;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Active work',
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
      const SizedBox(height: FwLayout.s2),
      const HonestNull('Reject changes a pending approval proposal only. '
          'Open Relay or Journey active work view for cancellation.'),
      if (snapshot.unavailable) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull(
            snapshot.unavailableReason ?? 'Active work status unavailable'),
      ] else ...[
        const SizedBox(height: FwLayout.s3),
        _runGroup('Active relay runs', snapshot.active,
            emptyMessage: 'No active relay runs reported.'),
        if (snapshot.terminal.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          _runGroup('Recent terminal relay runs', snapshot.terminal),
        ],
        if (snapshot.unknown.isNotEmpty) ...[
          const SizedBox(height: FwLayout.s3),
          _runGroup('Unknown relay run status', snapshot.unknown),
        ],
      ],
    ]);
  }

  Widget _runGroup(String title, List<ActiveWorkItem> items,
          {String? emptyMessage}) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style:
                const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
        if (items.isEmpty && emptyMessage != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull(emptyMessage),
        ],
        for (final item in items) ...[
          const SizedBox(height: FwLayout.s2),
          HairlineCard(
              child: Row(children: [
            VerdictDot(item.verdict, size: 7),
            const SizedBox(width: FwLayout.s2),
            Expanded(child: Text(item.label, overflow: TextOverflow.ellipsis)),
          ])),
        ],
      ]);
}

class _ProposalRow extends StatelessWidget {
  final GatewayGrantListItem item;
  final bool selected;
  final VoidCallback onTap;

  const _ProposalRow(
      {required this.item, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      recessed: selected,
      padding: EdgeInsets.zero,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(FwLayout.radius),
        child: Padding(
          padding: const EdgeInsets.all(FwLayout.s3),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(item.proposalRef, style: fwMono(t))),
              VerdictPill(item.derivedState, status: item.derivedState),
            ]),
            const SizedBox(height: FwLayout.s1),
            Text(_rowSubtitle(item),
                style: TextStyle(color: t.inkMuted, fontSize: 12.5)),
          ]),
        ),
      ),
    );
  }

  String _rowSubtitle(GatewayGrantListItem item) {
    final action = item.summaryText('action');
    final review = item.reviewAvailable ? 'review ready' : 'review unavailable';
    return [if (action.isNotEmpty) action, review].join(' · ');
  }
}

class _Facts extends StatelessWidget {
  final GatewayGrantListItem item;
  final GatewayGrantReview? review;
  const _Facts({required this.item, required this.review});

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: FwLayout.s3,
        runSpacing: FwLayout.s2,
        children: [
          HashText('record', item.recordSha256, keep: 14),
          if (item.reviewSha256.isNotEmpty)
            HashText('review', item.reviewSha256, keep: 14),
          if (item.operationRef.isNotEmpty)
            HashText('operation', item.operationRef, keep: 14),
          if (review != null) HashText('plan', review!.executionPlanSha256),
        ],
      );
}

class _ExactJsonBlock extends StatelessWidget {
  final GatewayGrantReview review;
  const _ExactJsonBlock({required this.review});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    const encoder = JsonEncoder.withIndent('  ');
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FwLayout.s3),
      decoration: BoxDecoration(
        color: t.ground2,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: t.hairline),
      ),
      child: SelectableText(encoder.convert(review.toExactJson()),
          style: fwMono(t, size: 11.5, color: t.ink), maxLines: null),
    );
  }
}
