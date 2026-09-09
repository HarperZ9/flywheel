"""Validate reviewed desktop font source and staged Windows payload bytes."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

SCHEMA = "flywheel.desktop-font-provenance/v1"
EXPECTED_FAMILIES = ["Cascadia Mono", "Hanken Grotesk"]
NOTICE_PATHS = {"licenses/FONT-PROVENANCE.json", "licenses/THIRD-PARTY-NOTICES.txt"}
CASCADIA_WEIGHTS = [200, 300, 400, 500, 600, 700]
CASCADIA_AXIS = {"min": 200, "default": 400, "max": 700}


def _refuse(message: str) -> None:
    raise ValueError(message)


def _load_helper_module():
    path = Path(__file__).with_name("font_provenance_payload.py")
    spec = importlib.util.spec_from_file_location("flywheel_font_provenance_payload", path)
    if spec is None or spec.loader is None:
        _refuse("font provenance payload helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HELPERS = _load_helper_module()


def _read_json(path: Path) -> dict:
    if not path.is_file():
        _refuse(f"missing {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _refuse(f"{path.name} is not a JSON object")
    return value


def _clean_yaml_value(line: str) -> str:
    return line.split(":", 1)[1].strip().strip("\"'")


def _pubspec_font_declarations(pubspec: Path) -> tuple[list[str], list[dict]]:
    families: list[str] = []
    rows: list[dict] = []
    family = ""
    current: dict | None = None
    for raw in pubspec.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("- family:"):
            family = _clean_yaml_value(line)
            families.append(family)
            current = None
        elif line.startswith("- asset: assets/fonts/"):
            current = {
                "family": family,
                "asset": _clean_yaml_value(line),
                "style": "normal",
                "weight": None,
            }
            rows.append(current)
        elif current is not None and line.startswith("weight:"):
            current["weight"] = int(_clean_yaml_value(line))
        elif current is not None and line.startswith("style:"):
            current["style"] = _clean_yaml_value(line)
    return families, rows


def _load_provenance(desktop_root: Path) -> dict:
    doc = _read_json(desktop_root / "release" / "FONT-PROVENANCE.json")
    if doc.get("schema") != SCHEMA:
        _refuse("FONT-PROVENANCE.json has the wrong schema")
    if not isinstance(doc.get("fonts"), list) or not doc["fonts"]:
        _refuse("FONT-PROVENANCE.json lists no fonts")
    return doc


def _require_no_conso(desktop_root: Path, *documents: object) -> None:
    for path in (desktop_root / "assets" / "fonts").glob("conso-*.ttf"):
        _refuse(f"Conso font file remains in desktop assets: {path.name}")
    payload = "\n".join(json.dumps(d, sort_keys=True) for d in documents)
    if "conso" in payload.lower():
        _refuse("Conso remains declared in font provenance or payload policy")


def _validate_notice_text(desktop_root: Path, fonts: list[dict]) -> None:
    notice = desktop_root / "release" / "THIRD-PARTY-NOTICES.txt"
    if not notice.is_file():
        _refuse("missing THIRD-PARTY-NOTICES.txt")
    text = notice.read_text(encoding="utf-8")
    required = [
        "Hanken Grotesk",
        "Cascadia Mono",
        "Copyright 2021 The Hanken Grotesk Project Authors",
        "Microsoft Corporation",
        "SIL OPEN FONT LICENSE Version 1.1",
    ]
    for token in required:
        if token not in text:
            _refuse(f"third-party notice lacks {token}")
    for row in fonts:
        if row["sha256"] not in text:
            _refuse(f"third-party notice lacks hash for {row['asset_path']}")


def _validate_cascadia_pubspec(rows: list[dict]) -> None:
    expected = (
        ("normal", "assets/fonts/CascadiaMono.ttf"),
        ("italic", "assets/fonts/CascadiaMonoItalic.ttf"),
    )
    for style, asset in expected:
        subset = [r for r in rows if r["family"] == "Cascadia Mono" and r["style"] == style]
        weights = sorted(r["weight"] for r in subset)
        assets = {r["asset"] for r in subset}
        if weights != CASCADIA_WEIGHTS or assets != {asset}:
            _refuse(f"Cascadia {style} weights are not declared explicitly")


def _validate_font_file(desktop_root: Path, row: dict, policy_rows: dict) -> dict | None:
    asset_path = row.get("asset_path")
    payload_path = "data/flutter_assets/" + str(asset_path)
    if row.get("payload_path") != payload_path:
        _refuse(f"wrong payload path for {asset_path}")
    if payload_path not in policy_rows:
        _refuse(f"font is missing from payload policy: {asset_path}")
    path = desktop_root / str(asset_path)
    if not path.is_file():
        _refuse(f"missing font asset: {asset_path}")
    raw = path.read_bytes()
    actual = {"sha256": _HELPERS.sha256(path), "size": path.stat().st_size}
    policy_row = policy_rows[payload_path]
    if row.get("sha256") != actual["sha256"] or row.get("size") != actual["size"]:
        _refuse(f"font provenance hash or size drifted: {asset_path}")
    if policy_row.get("sha256") != actual["sha256"] or policy_row.get("size") != actual["size"]:
        _refuse(f"payload policy hash or size drifted: {asset_path}")
    names = _HELPERS.name_values(raw)
    if row["family"] not in set().union(*names.values()):
        _refuse(f"font metadata lacks family name: {asset_path}")
    if "scripts.sil.org/OFL" not in " ".join(names.get(14, set())):
        _refuse(f"font metadata lacks the OFL URL: {asset_path}")
    weight, fs_type = _HELPERS.os2_fields(raw)
    if fs_type != 0:
        _refuse(f"font embedding fsType is restricted: {asset_path}")
    if row["family"] == "Hanken Grotesk" and row.get("weight") != weight:
        _refuse(f"Hanken weight metadata drifted: {asset_path}")
    if row["family"] == "Cascadia Mono":
        axis = _HELPERS.fvar_wght_axis(raw)
        if axis != CASCADIA_AXIS:
            _refuse(f"Cascadia wght axis drifted: {asset_path}")
        return axis
    return None


def validate_source(desktop_root: str | Path) -> dict:
    desktop_root = Path(desktop_root)
    provenance = _load_provenance(desktop_root)
    policy = _HELPERS.load_policy(desktop_root)
    _require_no_conso(desktop_root, provenance, policy)
    families, pubspec_rows = _pubspec_font_declarations(desktop_root / "pubspec.yaml")
    if sorted(set(families)) != EXPECTED_FAMILIES:
        _refuse(f"pubspec font families are not {EXPECTED_FAMILIES}")
    _validate_cascadia_pubspec(pubspec_rows)
    fonts = provenance["fonts"]
    asset_paths = [row.get("asset_path") for row in fonts]
    if not all(isinstance(path, str) for path in asset_paths):
        _refuse("FONT-PROVENANCE.json has a non-string asset path")
    declared_assets = [row["asset"] for row in pubspec_rows]
    if sorted(set(asset_paths)) != sorted(set(declared_assets)):
        _refuse("pubspec font assets do not match FONT-PROVENANCE.json")
    if len(set(asset_paths)) != len(asset_paths):
        _refuse("FONT-PROVENANCE.json has duplicate asset paths")
    actual_assets = _HELPERS.actual_source_font_assets(desktop_root)
    extra_assets = sorted(set(actual_assets) - set(asset_paths))
    if extra_assets:
        _refuse(f"extra source font asset: {extra_assets[0]}")
    missing_assets = sorted(set(asset_paths) - set(actual_assets))
    if missing_assets:
        _refuse(f"missing source font asset: {missing_assets[0]}")
    policy_rows = _HELPERS.expected_policy_rows(policy)
    cascadia_axis = None
    for row in fonts:
        axis = _validate_font_file(desktop_root, row, policy_rows)
        cascadia_axis = axis or cascadia_axis
    for notice_path in NOTICE_PATHS:
        row = policy_rows.get(notice_path)
        if row is None:
            _refuse(f"payload policy lacks required notice: {notice_path}")
        source = desktop_root / row["source_path"]
        if not source.is_file():
            _refuse(f"missing notice source: {row['source_path']}")
        if row["sha256"] != _HELPERS.sha256(source) or row["size"] != source.stat().st_size:
            _refuse(f"payload policy notice hash or size drifted: {notice_path}")
    _validate_notice_text(desktop_root, fonts)
    return {
        "schema": "flywheel.desktop-font-provenance-check/v1",
        "font_count": len(fonts),
        "families": EXPECTED_FAMILIES,
        "asset_paths": sorted(set(asset_paths)),
        "cascadia_pubspec_weights": CASCADIA_WEIGHTS,
        "cascadia_weight_axis": cascadia_axis,
    }


def validate_staged_payload(desktop_root: str | Path, staging_root: str | Path) -> dict:
    desktop_root = Path(desktop_root)
    staging_root = Path(staging_root)
    validate_source(desktop_root)
    allowed = _HELPERS.expected_policy_rows(_HELPERS.load_policy(desktop_root))
    relevant: set[str] = set()
    roots = [
        staging_root / "data" / "flutter_assets" / "assets" / "fonts",
        staging_root / "licenses",
    ]
    for base in roots:
        prefix = base.relative_to(staging_root).as_posix()
        for path in _HELPERS.manifest_relative_files(base):
            key = f"{prefix}/{path.as_posix()}"
            if base.name == "licenses" or path.suffix.lower() in _HELPERS.FONT_SUFFIXES:
                relevant.add(key)
    for expected, row in allowed.items():
        path = staging_root / expected
        if not path.is_file():
            _refuse(f"missing staged font/notice file: {expected}")
        if path.stat().st_size != row["size"] or _HELPERS.sha256(path) != row["sha256"]:
            _refuse(f"modified staged font/notice file: {expected}")
    for actual in sorted(relevant):
        if actual not in allowed:
            _refuse(f"extra staged font/notice file: {actual}")
    return {"schema": "flywheel.desktop-font-payload-check/v1", "match": True, "file_count": len(allowed)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    source = sub.add_parser("source")
    source.add_argument("--desktop-root", default=".")
    staging = sub.add_parser("staging")
    staging.add_argument("--desktop-root", default=".")
    staging.add_argument("--staging-root", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "source":
            result = validate_source(args.desktop_root)
        else:
            result = validate_staged_payload(args.desktop_root, args.staging_root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
