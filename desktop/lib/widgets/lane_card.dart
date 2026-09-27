// lane_card.dart - one lane on the Tools view, stated from the engine.
//
// Extracted from lane_health_panel.dart. The pill and the first line come
// from the row's `state` and the engine's sentence, never from the presence
// status: a lane that only answers its health check never reads "Ready" or
// "Runs" (H-2). A row kept from an earlier engine session reads "Last
// checked <time>" (H-10). A lane never checked offers Check, which probes
// that one lane.

import 'package:flutter/material.dart';

import '../models/gateway_models.dart';
import '../models/lane_identity.dart';
import '../models/lane_state.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class LaneCard extends StatelessWidget {
  final Lane lane;

  /// Probe this one lane now (`POST /api/lanes/<lane>/check`).
  final void Function(String name)? onCheck;
  const LaneCard({super.key, required this.lane, this.onCheck});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final id = laneIdentities[lane.name];
    final title = id?.title ?? lane.name;
    final key = laneCountKey(lane);
    return HairlineCard(
      padding: EdgeInsets.zero,
      child: Material(
        color: Colors.transparent,
        child: Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            tilePadding: const EdgeInsets.fromLTRB(
                FwLayout.s4, FwLayout.s3, FwLayout.s4, FwLayout.s2),
            childrenPadding: const EdgeInsets.fromLTRB(
                FwLayout.s4, 0, FwLayout.s4, FwLayout.s4),
            title: Row(children: [
              Expanded(
                child: Text(title,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 15.5, fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: FwLayout.s2),
              VerdictPill(laneStateLabel(lane),
                  status: laneCountVerdict(key)),
            ]),
            subtitle: _Summary(lane: lane, surface: id?.surface, onCheck: onCheck),
            children: [
              for (final item in lane.setup.where((i) => !i.met))
                _detailLine(t, 'setup', _setupText(item)),
              if (lane.mainAction.isNotEmpty)
                _detailLine(t, 'action', lane.mainAction),
              _detailLine(
                  t,
                  'runtime',
                  lane.detail.isEmpty
                      ? 'No runtime detail reported.'
                      : lane.detail),
              if (lane.code.isNotEmpty) _detailLine(t, 'code', lane.code),
              if (id != null) ...[
                _detailLine(t, 'role', '${lane.organ} · ${lane.role}'),
                _detailLine(t, 'identity', id.identity),
              ] else if (lane.organ.isNotEmpty || lane.role.isNotEmpty)
                _detailLine(t, 'role', '${lane.organ} · ${lane.role}'),
            ],
          ),
        ),
      ),
    );
  }
}

String _setupText(LaneSetupItem item) {
  if (item.title.isEmpty) return item.copy;
  if (item.copy.isEmpty) return item.title;
  return '${item.title}: ${item.copy}';
}

class _Summary extends StatelessWidget {
  final Lane lane;
  final String? surface;
  final void Function(String name)? onCheck;
  const _Summary({required this.lane, this.surface, this.onCheck});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final checked = laneCheckedLine(lane);
    final notChecked = laneCountKey(lane) == 'not_checked';
    final offerCheck = onCheck != null &&
        !isLaneHeld(lane) &&
        (notChecked || !lane.checkedThisSession);
    final soft = TextStyle(fontSize: 12.5, color: t.inkMuted, height: 1.4);
    return Padding(
      padding: const EdgeInsets.only(top: FwLayout.s2),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(laneSentence(lane),
            style: TextStyle(fontSize: 13.5, color: t.inkSoft, height: 1.4)),
        if (lane.secondLine.isNotEmpty) Text(lane.secondLine, style: soft),
        if (checked.isNotEmpty) Text(checked, style: soft),
        const SizedBox(height: FwLayout.s2),
        Wrap(
          spacing: FwLayout.s3,
          runSpacing: FwLayout.s1,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            _Fact(label: 'surface', value: surface ?? 'runtime lane'),
            _Fact(label: 'version', value: _versionText(lane)),
            _Fact(label: 'tools', value: _toolText(lane)),
            if (offerCheck)
              OutlinedButton(
                onPressed: () => onCheck!(lane.name),
                child: Text(notChecked ? 'Check' : 'Check again'),
              ),
          ],
        ),
      ]),
    );
  }
}

String _versionText(Lane lane) {
  if (lane.versionLabel.isNotEmpty) return lane.versionLabel;
  if (lane.installedVersion != null && lane.installedVersion!.isNotEmpty) {
    return lane.installedVersion!;
  }
  if (lane.expectedVersion.isNotEmpty) {
    return 'expects ${lane.expectedVersion}';
  }
  return lane.kind.isEmpty ? 'unknown' : lane.kind;
}

String _toolText(Lane lane) =>
    lane.tools == null ? 'not probed' : '${lane.tools} tools';

class _Fact extends StatelessWidget {
  final String label;
  final String value;
  const _Fact({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Text('$label $value', style: fwMono(t, size: 11, color: t.inkFaint));
  }
}

Widget _detailLine(FwTokens t, String label, String value) => Padding(
      padding: const EdgeInsets.only(top: FwLayout.s2),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 72,
          child: Text(label, style: fwMono(t, size: 11, color: t.inkFaint)),
        ),
        Expanded(
          child: Text(value,
              style: TextStyle(fontSize: 12.5, color: t.inkSoft, height: 1.4)),
        ),
      ]),
    );
