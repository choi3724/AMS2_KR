#!/usr/bin/env python3
"""Patch only the embedded DDS basename of the dedicated nameplate BFONT.

The dedicated file was renamed to kr13_driver_name_semibold.bfont while its
embedded name remained kr13_phoenix_body_regular.  AMS2 resolves DDS pages
through that embedded name, pairing the dedicated UV table with the wrong
atlas.  Both names are exactly 25 UTF-8 bytes, so the repair is an in-place
header substitution; glyph records, UVs, metrics, footer, DDS files, and file
size remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


ALIAS = "kr13_driver_name_semibold"
OLD_NAME = "kr13_phoenix_body_regular"
NEW_NAME = ALIAS


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("ams2_nameplate_name_parser", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import parser: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def font_path(root: Path, suffix: str) -> Path:
    nested = root / ALIAS / f"{ALIAS}{suffix}"
    return nested if nested.exists() else root / f"{ALIAS}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    parser_module = load_module(args.parser.resolve())
    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    report_path = args.report.resolve()
    if output_root.exists():
        raise RuntimeError(f"output already exists: {output_root}")
    shutil.copytree(input_root, output_root)

    source_path = font_path(input_root, ".bfont")
    output_path = font_path(output_root, ".bfont")
    before_raw = source_path.read_bytes()
    before = parser_module.parse_bfont(before_raw, str(source_path))
    if before.name != OLD_NAME:
        raise RuntimeError(f"unexpected embedded name: {before.name!r}")
    old_bytes = OLD_NAME.encode("utf-8")
    new_bytes = NEW_NAME.encode("utf-8")
    if len(old_bytes) != len(new_bytes):
        raise RuntimeError("minimal in-place contract requires equal byte lengths")
    name_offset = 20
    if before_raw[name_offset : name_offset + len(old_bytes)] != old_bytes:
        raise RuntimeError("embedded name bytes not found at BFONT header offset")
    after_raw = (
        before_raw[:name_offset]
        + new_bytes
        + before_raw[name_offset + len(old_bytes) :]
    )
    output_path.write_bytes(after_raw)
    after = parser_module.parse_bfont(after_raw, str(output_path))

    changed_offsets = [
        index for index, (left, right) in enumerate(zip(before_raw, after_raw)) if left != right
    ]
    semantic_contracts = {
        "file_size_unchanged": len(before_raw) == len(after_raw),
        "version_unchanged": before.version == after.version,
        "scale_unchanged": before.scale_bits == after.scale_bits,
        "header_fields_unchanged": (
            before.field_08,
            before.field_0c,
            before.field_after_name_1,
            before.field_after_name_2,
        ) == (
            after.field_08,
            after.field_0c,
            after.field_after_name_1,
            after.field_after_name_2,
        ),
        "glyph_count_unchanged": before.glyph_count == after.glyph_count,
        "codepoints_byte_exact": before.codepoint_bytes == after.codepoint_bytes,
        "uvs_byte_exact": before.uv_bytes == after.uv_bytes,
        "metrics_byte_exact": before.metric_bytes == after.metric_bytes,
        "footer_byte_exact": before.footer == after.footer,
        "line_height_baseline_unchanged": (before.line_height, before.baseline) == (after.line_height, after.baseline),
        "atlas_contract_unchanged": (before.atlas_count, before.glyphs_per_atlas) == (after.atlas_count, after.glyphs_per_atlas),
        "embedded_name_fixed": after.name == NEW_NAME,
        "changed_bytes_confined_to_name_field": bool(changed_offsets) and all(
            name_offset <= offset < name_offset + len(old_bytes) for offset in changed_offsets
        ),
    }
    dds_rows = []
    for page in range(after.atlas_count):
        source_dds = font_path(input_root, f"_{page:02d}.dds")
        output_dds = font_path(output_root, f"_{page:02d}.dds")
        dds_rows.append({
            "page": page,
            "source": str(source_dds),
            "output": str(output_dds),
            "source_sha256": sha256_path(source_dds),
            "output_sha256": sha256_path(output_dds),
            "byte_exact": source_dds.read_bytes() == output_dds.read_bytes(),
        })
    contracts = {
        **semantic_contracts,
        "all_dds_byte_exact": all(row["byte_exact"] for row in dds_rows),
    }
    status = "PASS" if all(contracts.values()) else "FAIL"
    report = {
        "schema": "ams2-kr-068.1-nameplate-embedded-name-minimal-fix-v1",
        "status": status,
        "root_cause": "Dedicated BFONT embedded name resolved Phoenix DDS pages instead of dedicated nameplate DDS pages",
        "input_root": str(input_root),
        "output_root": str(output_root),
        "bfont": {
            "input": str(source_path),
            "output": str(output_path),
            "before_sha256": sha256_path(source_path),
            "after_sha256": sha256_path(output_path),
            "before_embedded_name": before.name,
            "after_embedded_name": after.name,
            "name_offset": name_offset,
            "name_length": len(old_bytes),
            "changed_byte_count": len(changed_offsets),
            "changed_offsets": changed_offsets,
        },
        "dds": dds_rows,
        "contracts": contracts,
        "forbidden_changes": {
            "dds_changes": 0,
            "glyph_record_changes": 0,
            "uv_changes": 0,
            "metric_changes": 0,
            "footer_changes": 0,
            "igphasehud_changes": 0,
            "tdb_changes": 0,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "before_embedded_name": before.name,
        "after_embedded_name": after.name,
        "changed_bytes": len(changed_offsets),
        "bfont": str(output_path),
        "report": str(report_path),
    }, ensure_ascii=False))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
