"""ocsf_import.py -- OpenShell OCSF activity logs as sealed Flywheel records (OASP R2).

OpenShell writes OCSF v1.8.0 events as JSONL: gateway-side at the path set in
`[openshell.gateway.ocsf_log]`, sandbox-side at /var/log/openshell-ocsf.*.log.
Its docs call collection best-effort and the records are unsigned. This
importer reads one file, turns each event into a sealed, chained
`flywheel.openshell-event/v1` record in an import store, and closes the import
with one `flywheel.openshell-import/v1` summary record.

Mapping (per event): action Allowed is a MATCH for the network or process
fact; Denied or Blocked is a BLOCK evidence row; class 2004 (Detection
Finding) is a NOTICE for the owner's inbox; anything else is RECORDED.

Completeness (per import) is UNVERIFIABLE unless every condition holds: the
owner supplied a gateway metrics snapshot; the loss counters in it read zero (openshell_ocsf_log_dropped_total for every
reason, openshell_ocsf_log_writer_errors_total,
openshell_ocsf_log_recovery_discarded_bytes_total) and queued_total equals
written_total; every event came from the gateway (sandbox-local files have no
loss counters); and no line was malformed. Then completeness is MATCH, which
says only that the gateway counted no loss, not that the gateway saw
everything. Two limits the importer cannot check: a Prometheus scrape carries
no time, so the owner must take it after the last event in the file; and the
counters reset when the gateway restarts, so a restart inside the window can
hide loss. Any Application Lifecycle event (class 6002) in the file therefore
keeps completeness UNVERIFIABLE.

The seal proves what Flywheel read, not what OpenShell saw. Read the gateway
file from the host: the sandbox-local log is readable by the agent.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .contract import canonical_json, sha256_hex
from .records import HoldStore

EVENT_SCHEMA = "flywheel.openshell-event/v1"
IMPORT_SCHEMA = "flywheel.openshell-import/v1"
GATEWAY_PRODUCT = "OpenShell Gateway"
_LOSS = ("openshell_ocsf_log_dropped_total", "openshell_ocsf_log_writer_errors_total",
         "openshell_ocsf_log_recovery_discarded_bytes_total")
_METRIC = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eE]+|NaN|[+-]Inf)\s*")
DOES_NOT_PROVE = ("The seal shows what Flywheel read from the OCSF file. OpenShell records are "
                  "unsigned at source, so it does not show what OpenShell saw, and a MATCH on "
                  "completeness shows only that the gateway's loss counters read zero.")


def evidence_for(event: dict) -> str:
    if event.get("class_uid") == 2004:
        return "NOTICE"
    action = str(event.get("action") or event.get("disposition") or "")
    if action == "Allowed":
        return "MATCH"
    if action in ("Denied", "Blocked") or event.get("disposition") == "Blocked":
        return "BLOCK"
    return "RECORDED"


def _get(d: dict, *path):
    for key in path:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def event_record(event: dict, *, source_sha256: str, line_no: int) -> dict:
    endpoint = event.get("dst_endpoint") if isinstance(event.get("dst_endpoint"), dict) else {}
    return {
        "schema": EVENT_SCHEMA,
        "source": f"ocsf:{source_sha256[:16]}:{line_no}",
        "event_sha256": sha256_hex(canonical_json(event)),
        "metadata_uid": str(_get(event, "metadata", "uid") or ""),
        "container_uid": str(_get(event, "container", "uid") or ""),
        "product": str(_get(event, "metadata", "product", "name") or ""),
        "ocsf_version": str(_get(event, "metadata", "version") or ""),
        "time": int(event["time"]) if isinstance(event.get("time"), int) else 0,
        "class_uid": int(event["class_uid"]) if isinstance(event.get("class_uid"), int) else -1,
        "class_name": str(event.get("class_name", "")),
        "activity": str(event.get("activity_name", "")),
        "action": str(event.get("action", "")),
        "disposition": str(event.get("disposition", "")),
        "status_detail": str(event.get("status_detail", "")),
        "firewall_rule": str(_get(event, "firewall_rule", "name") or ""),
        "dst": {"domain": str(endpoint.get("domain", "")), "ip": str(endpoint.get("ip", "")),
                "port": int(endpoint["port"]) if isinstance(endpoint.get("port"), int) else 0},
        "actor_process": str(_get(event, "actor", "process", "name") or ""),
        "evidence": evidence_for(event),
    }


def parse_metrics(text: str) -> dict:
    """Prometheus text exposition to {name: summed value} (labels summed)."""
    out: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _METRIC.match(line)
        if m:
            out[m.group(1)] = out.get(m.group(1), 0.0) + float(m.group(3))
    return out


def completeness(metrics: dict | None, products: set, malformed: int,
                 lifecycle: int = 0) -> tuple:
    """(MATCH or UNVERIFIABLE, reasons)."""
    reasons = []
    if lifecycle:
        reasons.append(f"{lifecycle} lifecycle event(s) in the file; counters may have reset")
    if metrics is None:
        reasons.append("no gateway metrics snapshot supplied")
    else:
        for name in _LOSS:
            if name not in metrics:
                reasons.append(f"{name} absent from the snapshot")
            elif metrics[name] != 0:
                reasons.append(f"{name} = {metrics[name]:g}")
        queued = metrics.get("openshell_ocsf_log_queued_total")
        written = metrics.get("openshell_ocsf_log_written_total")
        if queued is None or written is None or queued != written:
            reasons.append("queued_total and written_total absent or unequal")
    if products - {GATEWAY_PRODUCT}:
        reasons.append("events from a non-gateway source have no loss counters")
    if malformed:
        reasons.append(f"{malformed} malformed line(s)")
    return ("UNVERIFIABLE" if reasons else "MATCH"), reasons


def _seen_uids(store: HoldStore) -> set:
    return {r.get("metadata_uid") for r in store.read_all(tolerant=True)
            if r.get("schema") == EVENT_SCHEMA and r.get("metadata_uid")}


def import_file(path, home, *, metrics_text: str | None = None) -> dict:
    """Import one OCSF JSONL file into the store at `home`. Re-importing skips
    events whose metadata.uid is already on record. Returns the summary record."""
    raw = Path(path).read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    store = HoldStore(home)
    seen = _seen_uids(store)
    counts = {"MATCH": 0, "BLOCK": 0, "NOTICE": 0, "RECORDED": 0}
    imported = skipped = malformed = lifecycle = 0
    products: set = set()
    times = []
    for line_no, line in enumerate(raw.decode("utf-8", "replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("not an object")
        except ValueError:
            malformed += 1
            continue
        rec = event_record(event, source_sha256=source_sha, line_no=line_no)
        products.add(rec["product"])
        if rec["metadata_uid"] and rec["metadata_uid"] in seen:
            skipped += 1
            continue
        store.append(rec)
        seen.add(rec["metadata_uid"])
        imported += 1
        counts[rec["evidence"]] += 1
        lifecycle += rec["class_uid"] == 6002
        if rec["time"]:
            times.append(rec["time"])
    metrics = parse_metrics(metrics_text) if metrics_text is not None else None
    verdict, reasons = completeness(metrics, products, malformed, lifecycle)
    summary = {"schema": IMPORT_SCHEMA, "source": f"ocsf-import:{source_sha[:16]}",
               "source_sha256": source_sha, "imported": imported,
               "skipped_duplicates": skipped, "malformed_lines": malformed,
               "evidence_counts": counts, "products": sorted(products),
               "first_time": min(times) if times else 0, "last_time": max(times) if times else 0,
               "metrics_sha256": sha256_hex(metrics_text.encode("utf-8")) if metrics_text else "",
               "completeness": verdict, "completeness_reasons": reasons,
               "does_not_prove": DOES_NOT_PROVE}
    store.append(summary)
    return summary
