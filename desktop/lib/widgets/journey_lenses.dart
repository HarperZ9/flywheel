import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/evidence_extensions.dart';
import '../models/journey_models.dart';
import '../theme/flywheel_theme.dart';
import 'evidence_extensions.dart';
import 'fw.dart';
import 'journey_cards.dart';

const _lenses = [JourneyLens.rescue, JourneyLens.diagnose, JourneyLens.verify];

String _lensName(JourneyLens lens) => switch (lens) {
      JourneyLens.rescue => 'Rescue',
      JourneyLens.diagnose => 'Diagnose',
      _ => 'Verify',
    };

IconData _lensIcon(JourneyLens lens) => switch (lens) {
      JourneyLens.rescue => Icons.restore,
      JourneyLens.diagnose => Icons.manage_search,
      _ => Icons.verified_user_outlined,
    };

class JourneyLensSelector extends StatefulWidget {
  const JourneyLensSelector({
    super.key,
    required this.selectedLens,
    required this.onSelected,
    this.enabled = true,
  });
  final JourneyLens selectedLens;
  final Future<void> Function(JourneyLens) onSelected;
  final bool enabled;

  @override
  State<JourneyLensSelector> createState() => _JourneyLensSelectorState();
}

class _JourneyLensSelectorState extends State<JourneyLensSelector> {
  late final List<FocusNode> _nodes;

  @override
  void initState() {
    super.initState();
    _nodes = List.generate(_lenses.length, (_) => FocusNode());
  }

  @override
  void dispose() {
    for (final node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  void _select(int index) {
    if (!widget.enabled) return;
    final next = index.clamp(0, _lenses.length - 1);
    _nodes[next].requestFocus();
    widget.onSelected(_lenses[next]);
  }

  Widget _button(BuildContext context, int index) {
    final lens = _lenses[index];
    final selected = lens == widget.selectedLens;
    final t = context.fw;
    final style = ButtonStyle(
      minimumSize: const WidgetStatePropertyAll(Size(44, 44)),
      padding: const WidgetStatePropertyAll(
          EdgeInsets.symmetric(horizontal: FwLayout.s3, vertical: FwLayout.s2)),
      foregroundColor: WidgetStatePropertyAll(t.inkSoft),
      backgroundColor: WidgetStatePropertyAll(selected ? t.ground2 : t.ground),
      shape: WidgetStatePropertyAll(RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(FwLayout.radiusSmall))),
      side: WidgetStateProperty.resolveWith((states) => BorderSide(
          color: states.contains(WidgetState.focused)
              ? t.ink
              : selected
                  ? t.inkMuted
                  : t.line,
          width: states.contains(WidgetState.focused) ? 2 : 1)),
    );
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.arrowLeft): () =>
            _select(index - 1),
        const SingleActivator(LogicalKeyboardKey.arrowUp): () =>
            _select(index - 1),
        const SingleActivator(LogicalKeyboardKey.arrowRight): () =>
            _select(index + 1),
        const SingleActivator(LogicalKeyboardKey.arrowDown): () =>
            _select(index + 1),
        const SingleActivator(LogicalKeyboardKey.home): () => _select(0),
        const SingleActivator(LogicalKeyboardKey.end): () =>
            _select(_lenses.length - 1),
      },
      child: Semantics(
        label: _lensName(lens),
        button: true,
        selected: selected,
        enabled: widget.enabled,
        onTap: widget.enabled ? () => widget.onSelected(lens) : null,
        excludeSemantics: true,
        child: OutlinedButton.icon(
          key: ValueKey('journey-lens-${lens.name}'),
          focusNode: _nodes[index],
          onPressed: widget.enabled ? () => widget.onSelected(lens) : null,
          style: style,
          icon: Icon(_lensIcon(lens), size: 18),
          label: Text(_lensName(lens)),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final buttons = [
            for (var index = 0; index < _lenses.length; index++)
              _button(context, index),
          ];
          if (constraints.maxWidth < 480) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final (index, button) in buttons.indexed) ...[
                  if (index > 0) const SizedBox(height: FwLayout.s2),
                  button,
                ],
              ],
            );
          }
          return Row(children: [
            for (final (index, button) in buttons.indexed) ...[
              if (index > 0) const SizedBox(width: FwLayout.s2),
              Expanded(child: button),
            ],
          ]);
        },
      );
}

class RescueLens extends StatelessWidget {
  const RescueLens({super.key, required this.projection});
  final JourneyProjection projection;

  @override
  Widget build(BuildContext context) {
    final actions = projection.nextActions
        .where((action) => action.kind != 'rollback')
        .toList(growable: false);
    final rollback = projection.nextActions
        .where((action) => action.kind == 'rollback')
        .toList(growable: false);
    return _LensColumn(children: [
      LensDetail(projection.detail),
      RecordSection(
        title: 'Next actions',
        emptyText: projection.nextActions.isEmpty
            ? 'No next action was supplied in this projection.'
            : 'No non-rollback next action was supplied in this projection.',
        children: [for (final action in actions) ActionRecord(action: action)],
      ),
      RecordSection(
        title: 'Rollback',
        emptyText: 'No rollback action was supplied in this projection.',
        children: [for (final action in rollback) ActionRecord(action: action)],
      ),
    ]);
  }
}

class LensDetail extends StatelessWidget {
  const LensDetail(this.detail, {super.key});
  final String detail;

  @override
  Widget build(BuildContext context) => detail.isEmpty
      ? const HonestNull('The server supplied no lens detail.')
      : HairlineCard(child: Text(detail));
}

class DiagnoseLens extends StatelessWidget {
  final JourneyProjection projection;

  /// Contextual extensions render only when the server advertises them;
  /// the lens never invents a surface for an absent capability.
  final EvidenceCapability? frontierCapability;
  final FrontierAxes? frontierAxes;
  const DiagnoseLens(
      {super.key,
      required this.projection,
      this.frontierCapability,
      this.frontierAxes});

  @override
  Widget build(BuildContext context) {
    List<Widget> verdicts(bool Function(String) accepts) => [
          for (final entry in projection.rawVerdicts.entries)
            if (accepts(entry.value)) LabeledValue(entry.key, entry.value),
        ];
    return _LensColumn(children: [
      LensDetail(projection.detail),
      if (frontierCapability != null)
        FrontierClaimExtension(
            capability: frontierCapability, axes: frontierAxes),
      RecordSection(
        title: 'Support',
        emptyText: 'No PASS verdicts were supplied in this projection.',
        children: verdicts((value) => value == 'PASS'),
      ),
      RecordSection(
        title: 'Contradictions',
        emptyText: 'No FAIL verdicts were supplied in this projection.',
        children: verdicts((value) => value == 'FAIL'),
      ),
      RecordSection(
        title: 'Unresolved',
        emptyText: 'No unresolved verdicts were supplied in this projection.',
        children: verdicts((value) => value != 'PASS' && value != 'FAIL'),
      ),
      RecordSection(
        title: 'Missing evidence',
        emptyText: 'No missing evidence was supplied in this projection.',
        children: [
          for (final item in projection.missingEvidence)
            MissingRecord(item: item),
        ],
      ),
    ]);
  }
}

class VerifyLens extends StatelessWidget {
  final JourneyProjection projection;

  /// Contextual extensions: frontier claims render in Verify too.
  final EvidenceCapability? frontierCapability;
  final FrontierAxes? frontierAxes;
  const VerifyLens(
      {super.key,
      required this.projection,
      this.frontierCapability,
      this.frontierAxes});

  @override
  Widget build(BuildContext context) {
    final conclusionLimit = projection.conclusion?['does_not_prove'];
    final limits = <Widget>[
      for (final check in projection.checks)
        if (check.doesNotProve.isNotEmpty)
          LabeledValue('Check ${check.checkId}', check.doesNotProve),
      if (conclusionLimit?.isNotEmpty ?? false)
        LabeledValue('Conclusion', conclusionLimit!),
    ];
    return _LensColumn(children: [
      LensDetail(projection.detail),
      if (frontierCapability != null)
        FrontierClaimExtension(
            capability: frontierCapability, axes: frontierAxes),
      RecordSection(
        title: 'Checks',
        emptyText: 'No checks were supplied in this projection.',
        children: [
          for (final check in projection.checks) CheckRecord(check: check),
        ],
      ),
      if (projection.checks.isEmpty)
        const HonestNull('No receipt refs were supplied in this projection.'),
      RecordSection(
        title: 'Limits',
        emptyText: 'No does_not_prove limits were supplied in this projection.',
        children: limits,
      ),
    ]);
  }
}

class _LensColumn extends StatelessWidget {
  const _LensColumn({required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (index, child) in children.indexed) ...[
            if (index > 0) const SizedBox(height: FwLayout.s4),
            child,
          ],
        ],
      );
}

class JourneyExtensionHost extends StatelessWidget {
  const JourneyExtensionHost({super.key, required this.lens});
  final JourneyLens lens;

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
