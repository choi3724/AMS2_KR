#!/usr/bin/env python3
"""Audit appended AI glyph identity and nameplate atlas-page hypotheses.

This tool is intentionally read-only.  It compares the PRE_MICROFIX and
current BFONT/DDS records, validates all appended codepoint identities, and
renders the same UV rectangle from every atlas page.  The latter is useful for
detecting a renderer that binds page 0..3 when a glyph record requests page 4.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


PLAYER_LIST = "kr13_phoenix_body_large"
NAMEPLATE = "kr13_driver_name_semibold"
TARGETS = tuple(map(ord, "콧밥톨"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def image_from_alpha(alpha: np.ndarray, scale: int = 10) -> Image.Image:
    height, width = alpha.shape
    image = Image.new("RGB", (max(1, width), max(1, height)), (32, 32, 32))
    white = Image.new("RGB", image.size, "white")
    image.paste(white, mask=Image.fromarray(alpha, mode="L"))
    return image.resize((max(1, width * scale), max(1, height * scale)), Image.Resampling.NEAREST)


def save_grid(path: Path, columns: list[tuple[str, Image.Image]]) -> None:
    label_height = 26
    gap = 8
    width = sum(image.width for _label, image in columns) + gap * (len(columns) - 1)
    height = label_height + max(image.height for _label, image in columns)
    canvas = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    x = 0
    for label, image in columns:
        draw.text((x + 2, 5), label, fill="white")
        canvas.paste(image, (x, label_height))
        x += image.width + gap
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def record(audit, font, pages, codepoint: int) -> dict:
    data = audit.glyph_data(font, pages, codepoint)
    index = data["index"]
    return {
        "codepoint": f"U+{codepoint:04X}",
        "character": chr(codepoint),
        "utf8_hex": chr(codepoint).encode("utf-8").hex().upper(),
        "utf16le_hex": chr(codepoint).encode("utf-16le").hex().upper(),
        "record_index": index,
        "page": data["page"],
        "page_local_index": index % font.glyphs_per_atlas,
        "rect": list(data["rect"]),
        "uv": list(data["uv"]),
        "metric": list(data["metric"]),
        "bitmap_sha256": sha256_bytes(data["alpha"].tobytes()),
        "active_pixels": int(np.count_nonzero(data["alpha"])),
        "analysis": data["analysis"],
        "alpha": data["alpha"],
    }


def public_record(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "alpha"}


def neighbors(font, index: int, radius: int = 3) -> list[dict]:
    rows = []
    for other in range(max(0, index - radius), min(font.glyph_count, index + radius + 1)):
        codepoint = font.codepoints[other]
        rows.append({
            "record_index": other,
            "codepoint": f"U+{codepoint:04X}",
            "character": chr(codepoint),
            "page": other // font.glyphs_per_atlas,
            "page_local_index": other % font.glyphs_per_atlas,
        })
    return rows


def same_rect_crop(audit, pages, page_index: int, rect: list[int]) -> np.ndarray:
    return audit.alpha_rect(pages[page_index], tuple(rect))


def nearest_glyphs(audit, font, pages, alpha: np.ndarray, limit: int = 8) -> list[dict]:
    candidates = []
    for codepoint in font.codepoints:
        glyph = audit.glyph_data(font, pages, codepoint)
        if glyph["alpha"].shape != alpha.shape:
            continue
        delta = np.abs(glyph["alpha"].astype(np.int16) - alpha.astype(np.int16))
        candidates.append({
            "codepoint": f"U+{codepoint:04X}",
            "character": chr(codepoint),
            "different_pixels": int(np.count_nonzero(delta)),
            "maximum_delta": int(delta.max(initial=0)),
            "mean_delta": float(delta.mean()),
            "bitmap_sha256": sha256_bytes(glyph["alpha"].tobytes()),
        })
    return sorted(candidates, key=lambda row: (row["mean_delta"], row["different_pixels"]))[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser", type=Path, required=True)
    parser.add_argument("--audit-module", type=Path, required=True)
    parser.add_argument("--pre-root", type=Path, required=True)
    parser.add_argument("--current-root", type=Path, required=True)
    parser.add_argument("--required-json", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    parser_module = load_module(args.parser.resolve(), "ams2_runtime_mapping_parser")
    audit = load_module(args.audit_module.resolve(), "ams2_runtime_mapping_audit")
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)

    required = json.loads(args.required_json.read_text(encoding="utf-8"))
    required_codepoints = [int(row["codepoint"][2:], 16) for row in required["missing_codepoints"]]
    routes = []
    identity_rows = []
    wrong_mappings = []
    for alias in (PLAYER_LIST, NAMEPLATE):
        pre_path, pre_font, pre_pages = audit.load_font_assets(parser_module, args.pre_root.resolve(), alias)
        current_path, current_font, current_pages = audit.load_font_assets(parser_module, args.current_root.resolve(), alias)
        route = {
            "alias": alias,
            "pre_bfont": str(pre_path),
            "pre_bfont_sha256": sha256_path(pre_path),
            "current_bfont": str(current_path),
            "current_bfont_sha256": sha256_path(current_path),
            "embedded_name": current_font.name,
            "version": current_font.version,
            "glyph_count": current_font.glyph_count,
            "atlas_count": current_font.atlas_count,
            "glyphs_per_atlas": current_font.glyphs_per_atlas,
            "line_height": current_font.line_height,
            "baseline": current_font.baseline,
            "bfont_byte_exact": pre_font.raw == current_font.raw,
            "embedded_name_matches_alias": current_font.name == alias,
            "targets": [],
        }
        embedded_assets = None
        if current_font.name != alias:
            embedded_bfont = audit.font_file(args.current_root.resolve(), current_font.name, ".bfont")
            if embedded_bfont.exists():
                embedded_assets = audit.load_font_assets(
                    parser_module, args.current_root.resolve(), current_font.name
                )
                route["embedded_name_resolves_to_existing_font"] = True
                route["embedded_resolved_bfont"] = str(embedded_assets[0])
                route["embedded_resolved_bfont_sha256"] = sha256_path(embedded_assets[0])
            else:
                route["embedded_name_resolves_to_existing_font"] = False
        applicable = [cp for cp in required_codepoints if cp in current_font.codepoints]
        for codepoint in applicable:
            pre = record(audit, pre_font, pre_pages, codepoint)
            current = record(audit, current_font, current_pages, codepoint)
            mapping_equal = all(
                pre[key] == current[key]
                for key in ("record_index", "page", "page_local_index", "rect", "uv", "metric")
            )
            bitmap_equal = np.array_equal(pre["alpha"], current["alpha"])
            row = {
                "alias": alias,
                "codepoint": f"U+{codepoint:04X}",
                "character": chr(codepoint),
                "mapping_equal": mapping_equal,
                "bitmap_equal": bitmap_equal,
                "pre_bitmap_sha256": pre["bitmap_sha256"],
                "current_bitmap_sha256": current["bitmap_sha256"],
                "classification": (
                    "BYTE_EXACT" if mapping_equal and bitmap_equal
                    else "RASTER_ONLY_CHANGE" if mapping_equal
                    else "MAPPING_CHANGE"
                ),
            }
            identity_rows.append(row)
            if not mapping_equal:
                wrong_mappings.append(row)

        for codepoint in TARGETS:
            pre = record(audit, pre_font, pre_pages, codepoint)
            current = record(audit, current_font, current_pages, codepoint)
            target = {
                "pre": public_record(pre),
                "current": public_record(current),
                "pre_neighbors": neighbors(pre_font, pre["record_index"]),
                "current_neighbors": neighbors(current_font, current["record_index"]),
                "mapping_byte_exact": all(
                    pre[key] == current[key]
                    for key in ("record_index", "page", "page_local_index", "rect", "uv", "metric")
                ),
                "bitmap_byte_exact": np.array_equal(pre["alpha"], current["alpha"]),
                "page_binding_hypotheses": [],
            }
            columns = []
            for page_index in range(current_font.atlas_count):
                sampled = same_rect_crop(audit, current_pages, page_index, current["rect"])
                target["page_binding_hypotheses"].append({
                    "sampled_page": page_index,
                    "rect": current["rect"],
                    "bitmap_sha256": sha256_bytes(sampled.tobytes()),
                    "active_pixels": int(np.count_nonzero(sampled)),
                    "nearest_declared_glyphs": nearest_glyphs(audit, current_font, current_pages, sampled),
                })
                columns.append((f"page{page_index}", image_from_alpha(sampled)))
            if embedded_assets is not None:
                _embedded_path, embedded_font, embedded_pages = embedded_assets
                requested_page = current["page"]
                if requested_page < len(embedded_pages):
                    sampled = same_rect_crop(
                        audit, embedded_pages, requested_page, current["rect"]
                    )
                    target["embedded_name_runtime_hypothesis"] = {
                        "resolved_alias": current_font.name,
                        "sampled_page": requested_page,
                        "rect": current["rect"],
                        "bitmap_sha256": sha256_bytes(sampled.tobytes()),
                        "active_pixels": int(np.count_nonzero(sampled)),
                        "nearest_declared_glyphs": nearest_glyphs(
                            audit, embedded_font, embedded_pages, sampled
                        ),
                    }
                    columns.append(
                        (f"embedded:{current_font.name}", image_from_alpha(sampled))
                    )
            save_grid(output / f"nameplate-page-hypothesis-{codepoint:04X}.png", columns)
            route["targets"].append(target)
        routes.append(route)

    changed = [row for row in identity_rows if row["classification"] != "BYTE_EXACT"]
    embedded_name_mismatches = [
        {
            "alias": route["alias"],
            "embedded_name": route["embedded_name"],
            "resolves_to_existing_font": route.get(
                "embedded_name_resolves_to_existing_font", False
            ),
        }
        for route in routes
        if not route["embedded_name_matches_alias"]
    ]
    failed = bool(wrong_mappings or embedded_name_mismatches)
    report = {
        "schema": "ams2-kr-068.1-nameplate-runtime-mapping-audit-v1",
        "scope_correction": {
            "player_list_runtime": "PASS_USER_CONFIRMED",
            "above_car_nameplate_runtime": "FAIL_USER_CONFIRMED",
            "policy": "Preserve player-list route; diagnose nameplate route only",
        },
        "targets": [
            {"codepoint": f"U+{cp:04X}", "character": chr(cp)} for cp in TARGETS
        ],
        "routes": routes,
        "appended_identity": {
            "requested_records": len(required_codepoints),
            "audited_route_records": len(identity_rows),
            "changed_records": changed,
            "wrong_mapping_records": wrong_mappings,
            "wrong_mapping_count": len(wrong_mappings),
        },
        "embedded_name_mismatches": embedded_name_mismatches,
        "static_verdict": (
            "BFONT_MAPPING_CORRUPTION_FOUND"
            if wrong_mappings
            else "EMBEDDED_DDS_BASENAME_MISMATCH_CONFIRMED"
            if embedded_name_mismatches
            else "BFONT_MAPPING_AND_DDS_BASENAME_PASS"
        ),
    }
    (output / "glyph-mapping-trace.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "appended-glyph-identity-validation.json").write_text(
        json.dumps(report["appended_identity"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "pre-microfix-vs-current-glyph-diff.json").write_text(
        json.dumps({"routes": routes, "changed_records": changed}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "FAIL" if failed else "PASS",
        "audited_route_records": len(identity_rows),
        "changed_records": len(changed),
        "wrong_mapping_count": len(wrong_mappings),
        "embedded_name_mismatch_count": len(embedded_name_mismatches),
        "output": str(output),
    }, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
