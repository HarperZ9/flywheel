import hashlib
import json
import os
import tarfile
from itertools import product
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "configs" / "qcr" / "amplitude-closure-manifest-v1.json"
RESEARCH_PATH = (
    ROOT / "docs" / "research" / "2026-07-21-quantum-classical-falsification-lanes.md"
)
LOCAL_SOURCE_ROOT = Path(
    os.environ.get(
        "QCR_SOURCE_ROOT", "C:/dev/scratch/qcr-2026-07-21-02/sources"
    )
)
LOCAL_SOURCE_RECEIPT = LOCAL_SOURCE_ROOT / "source-retrieval-receipt.json"

EXPECTED_SOURCES = {
    "aziz-howl-2510.19714v3": {
        "version": "2510.19714v3",
        "canonical_url": "https://arxiv.org/abs/2510.19714v3",
        "pdf_sha256": "a26fcb9f2add435c66ab6aa0ac86bcaf049481ee3c41e87e20cefc4dd63dc391",
        "source_bundle_sha256": "15dfdf6db4093aa12eb00e2416914e96dccddc3d0edba6169c3b3fefe93cbe32",
    },
    "gundhi-infantino-bassi-2604.19696v2": {
        "version": "2604.19696v2",
        "canonical_url": "https://arxiv.org/abs/2604.19696v2",
        "pdf_sha256": "34d1159cf786454a71b2fb380e470be52468e06854a93cdcb315787cbf161bbe",
        "source_bundle_sha256": "4e667a1d3c4dafbe319dc548bea1ca1ff6b885c15d307b023671bae91197865d",
    },
    "vidal-iyer-2607.03429v1": {
        "version": "2607.03429v1",
        "canonical_url": "https://arxiv.org/abs/2607.03429v1",
        "pdf_sha256": "2d90d1101b66c0cd868bd8a36fe8b41070e393a78902a8837111aa12dda52f99",
        "source_bundle_sha256": "404e6fa4b8419b541be6115cf18c6dab3cfe696ed726140f79ee2ef5f4a543ca",
    },
    "tang-et-al-2512.13675v2": {
        "version": "2512.13675v2",
        "canonical_url": "https://arxiv.org/abs/2512.13675v2",
        "pdf_sha256": "4c00093642a6a6caeb8535e1fbdd734af0156c8b43ce9e7326080794995f39ea",
        "source_bundle_sha256": "ef426c611f5ae32d80995c68c4a0d2181df0a867612afc8a7cf4c02e6c4c2938",
    },
}

EXPECTED_VARIANTS = {
    "same-field",
    "distinct-species",
    "full-no-pair-sector",
    "four-branch-projection",
    "particle-antiparticle-null",
    "barrier-control",
    "binding-localization-control",
}


def _load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _walk(value, path="$"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def _records_requiring_declarations(manifest):
    model = manifest["model"]
    yield from model["hamiltonians"]
    yield from model["actions"]
    yield model["initial_state"]
    yield from model["basis"]["sectors"]
    yield from manifest["variants"]
    yield from manifest["amplitudes"]
    yield from manifest["channels"]
    yield from manifest["evolution"]["records"]
    yield from manifest["oracles"]


def _require_local_source_corpus():
    if LOCAL_SOURCE_RECEIPT.is_file():
        return LOCAL_SOURCE_ROOT
    if "QCR_SOURCE_ROOT" in os.environ or str(ROOT).lower().startswith("c:\\dev\\"):
        pytest.fail(f"required local QCR source corpus is absent: {LOCAL_SOURCE_ROOT}")
    pytest.skip(
        "primary-source binaries are deliberately external; set QCR_SOURCE_ROOT to enforce"
    )


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_manifest_identity_and_exact_source_corpus():
    manifest = _load_manifest()

    assert manifest["schema"] == "qcr.amplitude-closure-manifest/v1"
    assert manifest["status"] == "populated_source_bounded_blocked_on_named_technical_gates"
    assert manifest["result_state"] == "protocol_only_not_executed"
    assert manifest["claims_physical_result"] is False

    sources = {row["source_id"]: row for row in manifest["sources"]}
    assert set(sources) == set(EXPECTED_SOURCES)
    for source_id, expected in EXPECTED_SOURCES.items():
        row = sources[source_id]
        assert row["version"] == expected["version"]
        assert row["canonical_url"] == expected["canonical_url"]
        assert row["pdf"]["sha256"] == expected["pdf_sha256"]
        assert row["source_bundle"]["sha256"] == expected["source_bundle_sha256"]


def test_manifest_declares_model_variants_and_exhaustive_symbolic_boundary():
    manifest = _load_manifest()
    model = manifest["model"]

    assert model["hamiltonians"]
    assert model["actions"]
    assert model["initial_state"]["branches"] == ["LL", "LR", "RL", "RR"]
    assert {row["sector_id"] for row in model["basis"]["sectors"]} >= {
        "full-no-pair-basis",
        "four-branch-projected-sector",
        "projection-complement-leakage-sector",
    }
    assert {row["variant_id"] for row in manifest["variants"]} == EXPECTED_VARIANTS

    perturbation = manifest["perturbation"]
    assert perturbation["orders"] == [0, 1, 2, 3, 4]
    assert perturbation["convention"] == "time_ordered_dyson_expansion"

    rule = manifest["completeness_rules"][0]
    assert rule["rule_id"] == "all-orders-0-through-4-all-inputs-all-full-basis-finals"
    assert rule["amplitude_definition"] == "A^(n)_{f;kl}=<f|U^(n)|initial kl>"
    assert rule["orders"] == [0, 1, 2, 3, 4]
    assert rule["initial_branches"] == ["LL", "LR", "RL", "RR"]
    assert rule["final_state_domain"] == "full-no-pair-basis"
    assert rule["projected_transition_count_per_order"] == 16
    assert rule["full_basis_enumeration_state"]["status"] == "unknown"

    expanded_projected_grid = {
        (order, row["initial_branch"], row["final_branch"])
        for row in manifest["projected_transitions"]
        for order in row["applies_to_orders"]
    }
    assert len(manifest["projected_transitions"]) == 16
    assert expanded_projected_grid == set(
        product(range(5), ("LL", "LR", "RL", "RR"), ("LL", "LR", "RL", "RR"))
    )

    assert {row["oracle_id"] for row in manifest["oracles"]} == {
        "O1",
        "O2",
        "O3",
        "O4",
        "O5",
        "O6",
    }


def test_amplitude_and_channel_rows_are_unique_complete_and_source_bound():
    manifest = _load_manifest()
    amplitudes = manifest["amplitudes"]
    amplitude_ids = [row["amplitude_id"] for row in amplitudes]

    assert len(amplitude_ids) == len(set(amplitude_ids))
    assert {(row["dyson_order"], row["initial_branch"]) for row in amplitudes} == set(
        product(range(5), ("LL", "LR", "RL", "RR"))
    )
    for row in amplitudes:
        assert row["final_sector"] == "full-no-pair-basis"
        assert row["final_state"] == "f in declared full-no-pair basis"
        assert row["species_assignment"]
        assert row["definition"] == "A^(n)_{f;kl}=<f|U^(n)|initial kl>"
        assert row["channel_ids"]
        assert row["variant_ids"]
        assert row["inclusion_state"] == "included"
        assert row["completeness_rule_id"] == (
            "all-orders-0-through-4-all-inputs-all-full-basis-finals"
        )

    channels = manifest["channels"]
    channel_ids = [row["channel_id"] for row in channels]
    assert len(channel_ids) == len(set(channel_ids))
    assert {row["inclusion_state"] for row in channels} >= {
        "included",
        "excluded",
        "disputed",
        "unknown_blocked",
    }
    referenced_channels = {
        channel_id for row in amplitudes for channel_id in row["channel_ids"]
    }
    assert referenced_channels <= set(channel_ids)

    amplitude_coverage = {
        channel_id: {
            (row["dyson_order"], row["initial_branch"])
            for row in amplitudes
            if channel_id in row["channel_ids"]
        }
        for channel_id in channel_ids
    }
    for channel in channels:
        assert channel["coverage_role"] in {
            "generator_channel",
            "zero_valued_audit",
            "classification_audit",
            "excluded_channel",
            "variant_control",
        }
        assert isinstance(channel["requires_amplitude_rows"], bool)
        if channel["requires_amplitude_rows"]:
            expected = set(
                product(channel["orders"], ("LL", "LR", "RL", "RR"))
            )
            assert amplitude_coverage[channel["channel_id"]] == expected
        else:
            assert not amplitude_coverage[channel["channel_id"]]


def test_channel_evidence_boundaries_separate_source_rows_from_protocol_extensions():
    manifest = _load_manifest()
    channels = {row["channel_id"]: row for row in manifest["channels"]}
    variants = {row["variant_id"]: row for row in manifest["variants"]}

    direct_source = channels["direct-local-background-scattering"]
    direct_extension = channels["direct-local-background-scattering-higher-order"]
    assert direct_source["orders"] == [1, 2]
    assert direct_source["declaration_ids"] == ["decl-ah-local-phase"]
    assert direct_extension["orders"] == [3, 4]
    assert "decl-ah-higher-order-local-phase" in direct_extension["declaration_ids"]

    self_source = channels["same-object-self-processes-second-order"]
    self_extension = channels["same-object-self-processes-higher-order"]
    assert self_source["orders"] == [2]
    assert "decl-ah-within-object-second-order" in self_source["declaration_ids"]
    assert self_extension["orders"] == [3, 4]
    for row in (self_source, self_extension):
        assert row["classification_relation"]["disjoint_from_parent"] is False
        assert row["classification_relation"]["additive_with_parent"] is False

    assert "decl-vidal-distinct-fields-abstract" in variants["distinct-species"][
        "declaration_ids"
    ]


def test_declaration_graph_resolves_to_hash_consistent_primary_sources():
    manifest = _load_manifest()
    sources = {row["source_id"]: row for row in manifest["sources"]}
    declarations = {
        row["declaration_id"]: row for row in manifest["source_declarations"]
    }

    assert len(declarations) == len(manifest["source_declarations"])
    for declaration_id, row in declarations.items():
        assert declaration_id
        source = sources[row["source_id"]]
        assert row["version"] == source["version"]
        assert row["canonical_url"] == source["canonical_url"]
        assert row["pdf_sha256"] == source["pdf"]["sha256"]
        assert row["source_bundle_sha256"] == source["source_bundle"]["sha256"]
        assert row["evidence_state"] in {
            "source_stated",
            "source_disputed",
            "source_bounded_protocol",
        }
        locus = row["locus"]
        assert locus["source_file"].endswith(".tex")
        assert locus.get("equation_labels") or locus.get("line_ranges")

    referenced = set()
    for record in _records_requiring_declarations(manifest):
        assert record["declaration_ids"], record
        referenced.update(record["declaration_ids"])
    assert referenced <= set(declarations)
    assert set(declarations) == referenced


def test_all_manifest_references_resolve_and_channel_orders_align():
    manifest = _load_manifest()
    declaration_ids = {row["declaration_id"] for row in manifest["source_declarations"]}
    variant_ids = {row["variant_id"] for row in manifest["variants"]}
    rule_ids = {row["rule_id"] for row in manifest["completeness_rules"]}
    gate_ids = {row["gate_id"] for row in manifest["technical_gates"]}
    channel_by_id = {row["channel_id"]: row for row in manifest["channels"]}
    orders = set(manifest["perturbation"]["orders"])

    assert len(gate_ids) == len(manifest["technical_gates"])
    for path, value in _walk(manifest):
        if not isinstance(value, dict):
            continue
        if value.get("status") == "unknown":
            assert value["required_review"] in gate_ids, path
        if "declaration_ids" in value:
            assert value["declaration_ids"], path
            assert set(value["declaration_ids"]) <= declaration_ids, path
        if "source_locus_declaration_id" in value:
            assert value["source_locus_declaration_id"] in value["declaration_ids"], path
        if "orders" in value:
            assert set(value["orders"]) <= orders, path
        if "applies_to_orders" in value:
            assert set(value["applies_to_orders"]) <= orders, path
        if "dyson_order" in value:
            assert value["dyson_order"] in orders, path

    for record in _records_requiring_declarations(manifest):
        assert set(record["declaration_ids"]) <= declaration_ids

    for record in (*manifest["amplitudes"], *manifest["channels"]):
        assert set(record["variant_ids"]) <= variant_ids
        assert record["completeness_rule_id"] in rule_ids
        assert record["source_locus_declaration_id"] in record["declaration_ids"]

    for row in manifest["amplitudes"]:
        assert row["dyson_order"] in orders
        for channel_id in row["channel_ids"]:
            assert channel_id in channel_by_id
            assert row["dyson_order"] in channel_by_id[channel_id]["orders"]
    for row in manifest["channels"]:
        assert set(row["orders"]) <= orders
        relation = row.get("classification_relation")
        if relation:
            parent = channel_by_id[relation["parent_channel"]]
            assert set(row["orders"]) <= set(parent["orders"])
    for row in manifest["projected_transitions"]:
        assert set(row["applies_to_orders"]) == orders
        assert set(row["declaration_ids"]) <= declaration_ids


def test_unknowns_tolerances_and_outputs_cannot_masquerade_as_results():
    manifest = _load_manifest()

    for path, value in _walk(manifest):
        assert value is not None, f"JSON null at {path}"
        if isinstance(value, dict) and value.get("status") == "unknown":
            assert value["reason"]
            assert value["evidence_state"] == "unverifiable"
            assert value["required_review"]

    tolerances = manifest["tolerances"]
    assert set(tolerances) == {"source_derived", "implementation_controls"}
    for row in tolerances["source_derived"]:
        if isinstance(row.get("value"), (int, float)):
            assert row["declaration_ids"]
    for row in tolerances["implementation_controls"]:
        if isinstance(row.get("value"), (int, float)):
            assert row["convergence_role"]
            assert row["not_source_claim"] is True

    assert manifest["outputs"]
    assert all(row["state"] == "declared_not_generated" for row in manifest["outputs"])
    assert all(row["exists"] is False for row in manifest["outputs"])


def test_local_source_receipt_and_primary_bytes_match_manifest():
    source_root = _require_local_source_corpus()
    manifest = _load_manifest()
    receipt = json.loads(LOCAL_SOURCE_RECEIPT.read_text(encoding="utf-8"))
    manifest_sources = {row["source_id"]: row for row in manifest["sources"]}
    receipt_sources = {row["source_id"]: row for row in receipt["sources"]}
    manifest_declarations = {
        row["declaration_id"]: row for row in manifest["source_declarations"]
    }
    receipt_declarations = {
        row["declaration_id"]: row for row in receipt["declarations"]
    }

    assert receipt["schema"] == "qcr.source-retrieval-receipt/v1"
    assert set(receipt_sources) == set(manifest_sources)
    for source_id, manifest_row in manifest_sources.items():
        receipt_row = receipt_sources[source_id]
        assert receipt_row["version"] == manifest_row["version"]
        assert receipt_row["abstract_url"] == manifest_row["canonical_url"]
        for artifact_type in ("pdf", "source_bundle"):
            manifest_artifact = manifest_row[artifact_type]
            receipt_artifact = receipt_row[artifact_type]
            artifact_path = source_root / receipt_artifact["path"]
            assert receipt_artifact["url"] == manifest_artifact["url"]
            assert receipt_artifact["bytes"] == manifest_artifact["bytes"]
            assert receipt_artifact["sha256"] == manifest_artifact["sha256"]
            assert artifact_path.stat().st_size == receipt_artifact["bytes"]
            assert _sha256(artifact_path) == receipt_artifact["sha256"]

    assert set(receipt_declarations) == set(manifest_declarations)
    for declaration_id, manifest_row in manifest_declarations.items():
        receipt_row = receipt_declarations[declaration_id]
        for field in (
            "source_id",
            "version",
            "canonical_url",
            "pdf_sha256",
            "source_bundle_sha256",
            "locus",
            "evidence_state",
        ):
            assert receipt_row[field] == manifest_row[field]


def test_local_extracted_tex_matches_source_bundles_and_resolves_loci():
    source_root = _require_local_source_corpus()
    receipt = json.loads(LOCAL_SOURCE_RECEIPT.read_text(encoding="utf-8"))
    sources = {row["source_id"]: row for row in receipt["sources"]}
    declarations = receipt["declarations"]

    checked_files = set()
    for declaration in declarations:
        source = sources[declaration["source_id"]]
        source_file = declaration["locus"]["source_file"]
        extracted_path = source_root / f'{source["version"]}-src' / source_file
        key = (declaration["source_id"], source_file)
        if key not in checked_files:
            with tarfile.open(source_root / source["source_bundle"]["path"], "r:*") as bundle:
                members = [
                    member
                    for member in bundle.getmembers()
                    if member.isfile() and Path(member.name).name == source_file
                ]
                assert len(members) == 1, key
                bundled = bundle.extractfile(members[0])
                assert bundled is not None
                assert hashlib.sha256(bundled.read()).hexdigest() == _sha256(extracted_path)
            checked_files.add(key)

        tex = extracted_path.read_text(encoding="utf-8")
        for label in declaration["locus"].get("equation_labels", []):
            assert tex.count(r"\label{" + label + "}") == 1, (
                declaration["declaration_id"],
                label,
            )
        lines = tex.splitlines()
        for line_range in declaration["locus"].get("line_ranges", []):
            bounds = line_range.split("-", 1)
            start = int(bounds[0])
            end = int(bounds[-1])
            assert 1 <= start <= end <= len(lines), (
                declaration["declaration_id"],
                line_range,
            )
            assert any(line.strip() for line in lines[start - 1 : end])


def test_research_lane_points_to_populated_but_blocked_manifest():
    text = RESEARCH_PATH.read_text(encoding="utf-8")

    assert "configs/qcr/amplitude-closure-manifest-v1.json" in text
    assert "Lane 1 readiness: POPULATED; BLOCKED ON NAMED TECHNICAL GATES" in text
    assert "schema: qcr.amplitude-closure-manifest/v1" not in text
