from __future__ import annotations

import hashlib

from .evidence_json import strict_load_json
from .inspect_python_units import enumerate_python_test_definitions
from .inspect_unit_contract_refs import DRIFT_REASONS as _DRIFT, PYTHON_TEST_UNIT as _PY_UNIT, analysis as _analysis, overlaps as _overlaps, pointer_value as _pointer_value, walk_refs as _walk_refs

SCHEMA = "flywheel.inspect-scorer-unit-contract/v1"
ADAPTER = "flywheel.python-test-definition-enumerator/v1"
MAX_BYTES = 8 * 1024 * 1024

def no_unit_contract() -> dict:
    return _analysis([], ["no_unit_contract"])

def verify_unit_contract(source_raw: bytes, sidecar_raw: bytes | None) -> dict:
    if sidecar_raw is None:
        return no_unit_contract()
    try:
        source = strict_load_json(source_raw, max_bytes=16 * 1024 * 1024, max_depth=32)
        sidecar = strict_load_json(sidecar_raw, max_bytes=MAX_BYTES, max_depth=96)
    except (TypeError, ValueError):
        return _analysis([], ["unit_contract_malformed"])
    return _Verifier(source_raw, source, sidecar).run()

class _Verifier:
    def __init__(self, source_raw: bytes, source: dict, sidecar: dict):
        self.raw, self.source, self.sidecar = source_raw, source, sidecar
        self.reasons: list[str] = []
        self.unsupported = False
        self.unverifiable = False
        self.partial = False
        self.pointer_refs = []
        self.observed: dict[tuple[str, str], tuple[int, int, str]] = {}

    def run(self) -> dict:
        if self.sidecar.get("schema") != SCHEMA:
            self._unsupported("unit_contract_malformed")
            return self._finish([])
        self._source_binding()
        contracts = self.sidecar.get("contracts")
        if type(contracts) is not list or not contracts:
            self._unsupported("unit_contract_malformed")
            return self._finish([])
        summaries = [self._contract(item) for item in contracts if type(item) is dict]
        if len(summaries) != len(contracts):
            self._unsupported("unit_contract_malformed")
        return self._finish(summaries)

    def _source_binding(self) -> None:
        src = self.sidecar.get("source")
        if type(src) is not dict:
            self._drift("source_hash_mismatch"); return
        if src.get("sha256") != hashlib.sha256(self.raw).hexdigest():
            self._drift("source_hash_mismatch")
        if src.get("byte_length") != len(self.raw):
            self._drift("source_byte_length_mismatch")
        if src.get("schema_version") != self.source.get("version"):
            self._drift("source_value_mismatch")

    def _contract(self, item: dict) -> dict:
        scorer = item.get("scorer") if type(item.get("scorer")) is dict else {}
        name = scorer.get("name") if type(scorer.get("name")) is str else ""
        impl = scorer.get("implementation") if type(scorer.get("implementation")) is dict else {}
        identity = "MATCH" if all(type(impl.get(k)) is str for k in ("package", "version", "source_sha256")) else "UNVERIFIABLE"
        actual = item.get("actual_score_measure") if type(item.get("actual_score_measure")) is dict else {}
        intended = item.get("declared_intended_measure") if type(item.get("declared_intended_measure")) is dict else {}
        aggregation = item.get("aggregation") if type(item.get("aggregation")) is dict else {}
        if intended.get("unit") != _PY_UNIT: self._drift("unsupported_declared_intended_unit")
        if aggregation and aggregation.get("input_unit") != _PY_UNIT: self._drift("unsupported_aggregation_input_unit")
        controls = item.get("mapping_controls") if type(item.get("mapping_controls")) is dict else {}
        coverage_scope = controls.get("coverage_scope") if controls.get("coverage_scope") in {"complete", "partial", "unknown"} else "unknown"
        if coverage_scope != "complete":
            self.partial = True; self._reason("partial_mapping")
        for ref in _walk_refs(item):
            self._check_pointer_ref(ref)
        observed, duplicates = self._adapter_observations(item.get("adapter_observations"))
        mapped, rows, overlaps, dup_ids, mapped_keys, mapping_out = self._mapping(
            item.get("source_item_mapping"), name)
        excl_count = self._exclusions(item.get("exclusions"), mapped_keys)
        if overlaps: self._drift("overlapping_selector")
        if dup_ids: self._drift("duplicate_unit_id")
        if duplicates: self._drift("duplicate_definition_name")
        scored_rows = self._scored_rows(name)
        if coverage_scope == "complete":
            if not scored_rows.issubset(rows):
                self._drift("omitted_definition_without_exclusion")
            if not rows.issubset(scored_rows):
                self._drift("source_value_mismatch")
        declared = intended.get("cardinality") if type(intended.get("cardinality")) is int else None
        actual_count = actual.get("cardinality") if type(actual.get("cardinality")) is int else None
        if mapped == 0 and declared not in (None, 0):
            self._drift("claimed_intended_unit_backed_only_by_sample_count")
        if coverage_scope == "complete" and observed != mapped + excl_count:
            self._drift("omitted_definition_without_exclusion")
        if declared != mapped + excl_count:
            self._drift("selector_completeness_unverified")
        relationship = self._relationship(actual.get("unit"), intended.get("unit"), actual_count, declared, aggregation)
        if relationship == "unverifiable" and actual.get("unit") != intended.get("unit"):
            self.unverifiable = True; self._reason("aggregation_missing")
        return {"scorer": name, "actual_score_unit": actual.get("unit"),
                "actual_score_cardinality": actual_count,
                "declared_intended_unit": intended.get("unit"),
                "declared_intended_cardinality": declared,
                "source_rows": len(scored_rows), "scored_source_rows_for_named_scorer": len(scored_rows),
                "covered_source_rows": len(rows), "excluded_source_rows": excl_count,
                "mapped_definitions": mapped,
                "omitted_definitions": max(0, observed - mapped - excl_count),
                "duplicate_definitions": len(duplicates) + len(dup_ids),
                "overlapping_selectors": overlaps, "coverage_scope": coverage_scope,
                "selector_completeness": controls.get("selector_completeness", "unknown"),
                "source_item_mapping": mapping_out,
                "aggregation": relationship.replace("-", "_"),
                "identity_status": identity, "_relationship": relationship}

    def _adapter_observations(self, observations: object) -> tuple[int, set[str]]:
        if type(observations) is not list:
            self.unverifiable = True; self._reason("adapter_observation_missing"); return 0, set()
        total, duplicates = 0, set()
        for obs in observations:
            if type(obs) is not dict or obs.get("adapter") != ADAPTER:
                self.unsupported = True; self._reason("adapter_observation_missing"); continue
            text = self._container(obs.get("container_pointer"), obs.get("container_value_sha256"))
            if text is None: continue
            found = enumerate_python_test_definitions(text)
            if found["status"] == "parse_error":
                self.unsupported = True; self._reason("adapter_parse_error"); continue
            if found["nested_definitions_unsupported"]:
                self.unsupported = True; self._reason("adapter_unsupported_nested_definition")
            if obs.get("observed_definitions") != len(found["definitions"]):
                self._drift("selector_completeness_unverified")
            declared_dups = set(obs.get("duplicate_definition_names") or [])
            actual_dups = set(found["duplicate_definition_names"])
            if declared_dups != actual_dups or actual_dups:
                duplicates.update(actual_dups or declared_dups)
            for definition in found["definitions"]:
                span = definition["span"]
                self.observed[(obs["container_pointer"], definition["unit_id"])] = (
                    span["start"], span["end"], definition["source_value_sha256"])
            total += len(found["definitions"])
        return total, duplicates

    def _mapping(self, mapping: object, scorer: str) -> tuple[int, set[int], int, set[str], set[tuple[str, str]], list]:
        if type(mapping) is not list:
            self._drift("claimed_intended_unit_backed_only_by_sample_count"); return 0, set(), 0, set(), set(), []
        spans, seen_ids, dup_ids, rows, mapped, mapped_keys, mapping_out = [], set(), set(), set(), 0, set(), []
        for row in mapping:
            if type(row) is not dict: continue
            src = row.get("source_row") if type(row.get("source_row")) is dict else {}
            row_index = self._row_index(src, scorer)
            if row_index is not None:
                rows.add(row_index)
            defs = row.get("mapped_definitions") if type(row.get("mapped_definitions")) is dict else {}
            refs = defs.get("refs") if type(defs.get("refs")) is list else []
            out_refs = []
            if defs.get("unit") != _PY_UNIT: self._drift("unsupported_mapped_definition_unit")
            if defs.get("count") != len(refs):
                self._drift("selector_completeness_unverified")
            mapped += len(refs)
            for ref in refs:
                if type(ref) is not dict: continue
                unit_id = ref.get("unit_id")
                if type(unit_id) is str:
                    (dup_ids if unit_id in seen_ids else seen_ids).add(unit_id)
                span = self._check_span(ref.get("source") if type(ref.get("source")) is dict else {}, unit_id)
                if span:
                    spans.append((span[0], span[1], span[2], unit_id))
                    if type(unit_id) is str:
                        mapped_keys.add((span[0], unit_id))
                    out_refs.append({"unit_id": unit_id, "source": self._span_source(ref["source"])})
            mapping_out.append({"source_row": self._row_source(src),
                                "mapped_definitions": {"unit": defs.get("unit"),
                                                       "count": len(out_refs),
                                                       "refs": out_refs}})
        return mapped, rows, _overlaps(spans), dup_ids, mapped_keys, mapping_out

    def _row_source(self, row: dict) -> dict:
        return {k: row[k] for k in ("sample_index", "sample_id", "sample_id_ref", "epoch_ref", "score_ref") if k in row}

    def _span_source(self, source: dict) -> dict:
        return {k: source[k] for k in ("container_pointer", "container_value_sha256",
                                       "span", "source_value", "source_value_sha256") if k in source}

    def _exclusions(self, exclusions: object, mapped_keys: set[tuple[str, str]]) -> int:
        if type(exclusions) is not list:
            return 0
        count, seen = 0, set()
        for item in exclusions:
            if type(item) is not dict or type(item.get("unit_id")) is not str:
                self._drift("selector_completeness_unverified"); continue
            if type(item.get("reason")) is not str or not item["reason"].strip():
                self._drift("exclusion_reason_missing"); continue
            span = self._check_span(item.get("source") if type(item.get("source")) is dict else {}, item["unit_id"])
            key = (span[0], item["unit_id"]) if span else None
            if key is None or key in mapped_keys or key in seen:
                self._drift("selector_completeness_unverified"); continue
            seen.add(key); count += 1
        return count

    def _check_span(self, src: dict, unit_id: object) -> tuple[str, int, int] | None:
        text = self._container(src.get("container_pointer"), src.get("container_value_sha256"))
        span = src.get("span") if type(src.get("span")) is dict else {}
        start, end = span.get("start"), span.get("end")
        bad = text is None or span.get("encoding") != "json-string-codepoints-v1"
        bad = bad or type(start) is not int or type(end) is not int or start < 0 or end < start
        if bad or end > len(text):
            self._drift("span_out_of_range"); return None
        value = text[start:end]
        if src.get("source_value") != value:
            self._drift("span_source_value_mismatch")
        if src.get("source_value_sha256") != hashlib.sha256(value.encode("utf-8")).hexdigest():
            self._drift("span_source_value_sha256_mismatch")
        observed = self.observed.get((src.get("container_pointer"), unit_id))
        if type(unit_id) is not str or observed != (start, end, hashlib.sha256(value.encode("utf-8")).hexdigest()):
            self._drift("selector_completeness_unverified")
        return src.get("container_pointer"), start, end

    def _row_index(self, row: dict, scorer: str) -> int | None:
        index = row.get("sample_index")
        samples = self.source.get("samples") if type(self.source.get("samples")) is list else []
        if type(index) is not int or index < 0 or index >= len(samples) or type(samples[index]) is not dict:
            self._drift("source_value_mismatch"); return None
        expected = {
            "sample_id_ref": f"/samples/{index}/id",
            "epoch_ref": f"/samples/{index}/epoch",
            "score_ref": f"/samples/{index}/scores/{scorer}/value",
        }
        for key, pointer in expected.items():
            ref = row.get(key) if type(row.get(key)) is dict else {}
            if ref.get("json_pointer") != pointer:
                self._drift("source_value_mismatch"); return None
        if type(samples[index].get("scores")) is not dict or scorer not in samples[index]["scores"]:
            self._drift("source_value_mismatch"); return None
        return index

    def _container(self, pointer: object, digest: object) -> str | None:
        if type(pointer) is not str or type(digest) is not str:
            self._drift("pointer_missing"); return None
        try:
            value = _pointer_value(self.source, pointer)
        except (KeyError, IndexError, ValueError, TypeError):
            self._drift("pointer_missing"); return None
        if type(value) is not str:
            self.unsupported = True; self._reason("adapter_parse_error"); return None
        if hashlib.sha256(value.encode("utf-8")).hexdigest() != digest:
            self._drift("span_source_value_sha256_mismatch")
        return value

    def _check_pointer_ref(self, ref: dict) -> None:
        try:
            value = _pointer_value(self.source, ref["json_pointer"])
        except (KeyError, IndexError, ValueError, TypeError):
            self._drift("pointer_missing"); return
        kept = {"json_pointer": ref["json_pointer"], "source_value": ref.get("source_value")}
        self.pointer_refs.append(kept)
        if value != ref.get("source_value"):
            self._drift("source_value_mismatch")

    def _scored_rows(self, scorer: str) -> set[int]:
        samples = self.source.get("samples") if type(self.source.get("samples")) is list else []
        return {i for i, sample in enumerate(samples) if type(sample) is dict
                and type(sample.get("scores")) is dict and scorer in sample["scores"]}

    def _relationship(self, actual_unit, intended_unit, actual_count, declared, aggregation: dict) -> str:
        if actual_unit == intended_unit: return "same-unit"
        if aggregation.get("mode") == "many_to_one": return "many-to-one"
        if aggregation.get("mode") == "one_to-one" or aggregation.get("mode") == "one_to_one": return "one-to-one"
        if actual_count is not None and declared is not None and actual_count == declared:
            return "one-to-one"
        return "unverifiable"

    def _finish(self, summaries: list[dict]) -> dict:
        status = "MATCH"
        if self.unsupported: status = "UNSUPPORTED"
        elif any(code in _DRIFT for code in self.reasons): status = "DRIFT"
        elif self.partial: status = "DRIFT"
        elif self.unverifiable: status = "UNVERIFIABLE"
        for summary in summaries:
            relationship = summary.pop("_relationship", "unverifiable")
            mapped_units = summary.get("mapped_definitions")
            summary["mapping_consistency"] = {"status": status, "reason_codes": list(self.reasons)}
            summary["score_unit_relationship"] = {
                "status": relationship,
                "actual_score_unit": summary.get("actual_score_unit"),
                "mapped_unit": summary.get("declared_intended_unit"),
                "actual_scored_units": summary.get("actual_score_cardinality"),
                "mapped_units": mapped_units,
            }
            summary["definition_score_coverage"] = {"status": "UNVERIFIABLE",
                                                    "reason_codes": ["no_per_definition_score_evidence"],
                                                    "scored_definitions": None}
        return _analysis(summaries, self.reasons, self.pointer_refs)

    def _reason(self, code: str) -> None:
        if code not in self.reasons: self.reasons.append(code)
    def _drift(self, code: str) -> None: self._reason(code)
    def _unsupported(self, code: str) -> None:
        self.unsupported = True; self._reason(code)
