// gateway_models.dart — typed models for the Flywheel gateway API.
//
// These mirror the JSON shapes returned by the Python gateway's /api/* routes.
// Each model has a fromJson factory; the gateway returns deterministic JSON so
// we parse defensively (missing fields degrade to defaults, never crash).

/// A single lane in the lane roster (GET /api/lanes).
class Lane {
  final String name;
  final String kind;
  final String? installedVersion;
  final String expectedVersion;
  final String status; // live | declared | missing | stale
  final String organ;
  final String role;
  final String detail;
  final int? tools; // MCP tool count, present only after a real probe

  Lane({
    required this.name,
    required this.kind,
    this.installedVersion,
    required this.expectedVersion,
    required this.status,
    required this.organ,
    required this.role,
    required this.detail,
    this.tools,
  });

  factory Lane.fromJson(Map<String, dynamic> j) => Lane(
        name: j['name'] ?? '',
        kind: j['kind'] ?? '',
        installedVersion: j['installed_version'],
        expectedVersion: j['expected_version'] ?? '',
        status: j['status'] ?? 'missing',
        organ: j['organ'] ?? '',
        role: j['role'] ?? '',
        detail: j['detail'] ?? '',
        tools: j['tools'] is int ? j['tools'] : null,
      );

  bool get isLive => status == 'live';
  bool get isDeclared => status == 'declared';
  bool get isMissing => status == 'missing';
}

/// The full lane roster (GET /api/lanes).
class LaneRoster {
  final int nLanes;
  final Map<String, int> byStatus;
  final bool allLive;
  final List<Lane> lanes;

  LaneRoster({
    required this.nLanes,
    required this.byStatus,
    required this.allLive,
    required this.lanes,
  });

  factory LaneRoster.fromJson(Map<String, dynamic> j) => LaneRoster(
        nLanes: j['n_lanes'] ?? 0,
        byStatus: Map<String, int>.from(j['by_status'] ?? {}),
        allLive: j['all_live'] ?? false,
        lanes: ((j['lanes'] ?? []) as List)
            .map((e) => Lane.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

/// A spine organ from the projected world (GET /api/world).
class SpineDoc {
  final Map<String, String> organs;
  final List<String> flagships;
  final Map<String, String> routes;
  final bool closed;
  final String reconciler;

  SpineDoc({
    required this.organs,
    required this.flagships,
    required this.routes,
    required this.closed,
    required this.reconciler,
  });

  factory SpineDoc.fromJson(Map<String, dynamic> j) => SpineDoc(
        organs: Map<String, String>.from(j['organs'] ?? {}),
        flagships: List<String>.from(j['flagships'] ?? []),
        routes: Map<String, String>.from(j['routes'] ?? {}),
        closed: j['closed'] ?? false,
        reconciler: j['reconciler'] ?? '',
      );
}

/// The projected world (GET /api/world) — the root-hashed state snapshot.
class WorldDoc {
  final String schema;
  final String rootHash;
  final String? merkleRoot;
  final SpineDoc? spine;
  final Map<String, dynamic> findings;
  final Map<String, dynamic> cursor;

  WorldDoc({
    required this.schema,
    required this.rootHash,
    this.merkleRoot,
    this.spine,
    required this.findings,
    required this.cursor,
  });

  factory WorldDoc.fromJson(Map<String, dynamic> j) => WorldDoc(
        schema: j['schema'] ?? '',
        rootHash: j['root_hash'] ?? '',
        merkleRoot: j['merkle_root'],
        spine: j['spine'] is Map<String, dynamic>
            ? SpineDoc.fromJson(j['spine'])
            : null,
        findings: Map<String, dynamic>.from(j['findings'] ?? {}),
        cursor: Map<String, dynamic>.from(j['cursor'] ?? {}),
      );
}

/// A companion routing result (POST /api/companion).
class CompanionResult {
  final String source; // cache | local-verified | local-consensus | escalate
  final String? text;
  final String? escalateTo;
  final String? bestEffortText;
  final String? receipt;
  final String? verdict;

  CompanionResult({
    required this.source,
    this.text,
    this.escalateTo,
    this.bestEffortText,
    this.receipt,
    this.verdict,
  });

  factory CompanionResult.fromJson(Map<String, dynamic> j) => CompanionResult(
        source: j['source'] ?? '',
        text: j['text'],
        escalateTo: j['escalate_to'],
        bestEffortText: j['best_effort_text'],
        receipt: j['receipt'],
        verdict: j['verdict'],
      );

  bool get escalated => source == 'escalate';
}

/// One in-repo catalog receipt (GET /api/receipts).
class CatalogReceipt {
  final String path;
  final String sha256;
  final int? size;
  final bool present;

  CatalogReceipt(
      {required this.path,
      required this.sha256,
      this.size,
      required this.present});

  factory CatalogReceipt.fromJson(Map<String, dynamic> j) => CatalogReceipt(
        path: j['path'] ?? '',
        sha256: j['sha256'] ?? '',
        size: j['size'],
        present: j['present'] ?? false,
      );
}

/// One accepted proof envelope (GET /api/receipts).
class EnvelopeReceipt {
  final String name;
  final String verdict; // PASS | FAIL | UNREADABLE | ?
  final String taskId;
  final String sha256;
  final int? size;

  EnvelopeReceipt(
      {required this.name,
      required this.verdict,
      required this.taskId,
      required this.sha256,
      this.size});

  factory EnvelopeReceipt.fromJson(Map<String, dynamic> j) => EnvelopeReceipt(
        name: j['name'] ?? '',
        verdict: j['verdict'] ?? '?',
        taskId: j['task_id'] ?? '',
        sha256: j['sha256'] ?? '',
        size: j['size'],
      );
}

/// The receipts ledger (GET /api/receipts).
class ReceiptsLedger {
  final List<CatalogReceipt> catalog;
  final int catalogPresent;
  final List<EnvelopeReceipt> envelopes;
  final int envelopeCount;
  final int passCount;

  ReceiptsLedger(
      {required this.catalog,
      required this.catalogPresent,
      required this.envelopes,
      required this.envelopeCount,
      required this.passCount});

  factory ReceiptsLedger.fromJson(Map<String, dynamic> j) => ReceiptsLedger(
        catalog: ((j['catalog'] ?? []) as List)
            .map((e) => CatalogReceipt.fromJson(e as Map<String, dynamic>))
            .toList(),
        catalogPresent: j['catalog_present'] ?? 0,
        envelopes: ((j['envelopes'] ?? []) as List)
            .map((e) => EnvelopeReceipt.fromJson(e as Map<String, dynamic>))
            .toList(),
        envelopeCount: j['envelope_count'] ?? 0,
        passCount: j['pass_count'] ?? 0,
      );
}

/// A provider endpoint row (GET /api/endpoints).
class EndpointRow {
  final String name;
  final String backend;
  final String credential; // present | absent | local-none | cli-auth
  final String providerRole;
  final bool configured;

  EndpointRow({
    required this.name,
    required this.backend,
    required this.credential,
    required this.providerRole,
    required this.configured,
  });

  factory EndpointRow.fromJson(Map<String, dynamic> j) => EndpointRow(
        name: j['name'] ?? j['model'] ?? '',
        backend: j['backend'] ?? '',
        credential: j['credential'] ?? 'absent',
        providerRole: j['provider_role'] ?? '',
        configured: j['configured'] ?? false,
      );

  bool get hasCredential => credential == 'present' || credential == 'cli-auth';
}
