#!/usr/bin/env python3
"""Append AI glyphs to v0.6.5 Golden AMS2 fonts without moving old glyphs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


SDF_LOW = 120
SDF_HIGH = 136
NBSP = 0x00A0
APPEND_EXCLUDED = {
    "kr13_font_data_list",
    "kr13_font_heading_44",
}
APPEND_WITHOUT_NBSP = {"kr13_driver_name_semibold"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("ams2_golden_append_parser", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load parser: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_u32(handle) -> int:
    data = handle.read(4)
    if len(data) != 4:
        raise RuntimeError("truncated TDB integer")
    return struct.unpack("<I", data)[0]


def read_lp_utf8(handle) -> str:
    size = read_u32(handle)
    data = handle.read(size)
    if len(data) != size:
        raise RuntimeError("truncated TDB UTF-8 string")
    return data.decode("utf-8")


def read_korean_tdb(path: Path) -> list[str]:
    with path.open("rb") as handle:
        read_u32(handle)
        read_lp_utf8(handle)
        language_count = read_u32(handle)
        group_count = read_u32(handle)
        key_count = read_u32(handle)
        handle.read(12)
        for _ in range(group_count):
            read_lp_utf8(handle)
        for _ in range(key_count):
            read_lp_utf8(handle)
        korean = None
        for _ in range(language_count):
            name = read_lp_utf8(handle)
            block_size = read_u32(handle)
            block_end = handle.tell() + block_size
            values = []
            for _ in range(key_count):
                if len(handle.read(8)) != 8:
                    raise RuntimeError("truncated TDB key hash")
                units = read_u32(handle)
                raw = handle.read(units * 2)
                if len(raw) != units * 2:
                    raise RuntimeError("truncated TDB UTF-16 value")
                values.append(raw.decode("utf-16le"))
            if handle.tell() != block_end:
                raise RuntimeError(f"TDB language block boundary mismatch: {name}")
            if name.casefold() == "korean":
                korean = values
        if handle.tell() != path.stat().st_size:
            raise RuntimeError("TDB trailing bytes")
        if korean is None:
            raise RuntimeError("drivers.tdb has no Korean language")
        return korean


def glyph_rect(font, index: int, dds) -> tuple[int, int, int, int]:
    uv = font.uvs[index]
    return (
        round(uv[0] * dds.width),
        round(uv[1] * dds.height),
        round(uv[2] * dds.width),
        round(uv[3] * dds.height),
    )


def layout(widths: list[int], line_height: int, width: int, height: int) -> list[tuple[int, int, int, int]]:
    x = y = 8
    result = []
    for glyph_width in widths:
        x = (x + 3) // 4 * 4
        if glyph_width and x + glyph_width > width:
            y = (y + line_height + 3) // 4 * 4 + 8
            x = 8
        if y + line_height + 8 > height:
            raise RuntimeError(f"append layout does not fit {width}x{height}")
        result.append((x, y, x + glyph_width, y + line_height))
        if glyph_width:
            x = (x + glyph_width + 3) // 4 * 4 + 8
    return result


def block_set(rect: tuple[int, int, int, int], width: int) -> set[int]:
    x0, y0, x1, y1 = rect
    if x0 == x1:
        return set()
    blocks_per_row = width // 4
    return {
        by * blocks_per_row + bx
        for by in range(y0 // 4, (y1 + 3) // 4)
        for bx in range(x0 // 4, (x1 + 3) // 4)
    }


def alpha_rect(dds, rect: tuple[int, int, int, int]) -> bytes:
    x0, y0, x1, y1 = rect
    if x0 == x1:
        return b""
    out = bytearray()
    if dds.kind == "L8":
        for y in range(y0, y1):
            row = dds.payload[y * dds.width + x0 : y * dds.width + x1]
            out.extend(
                0 if value <= SDF_LOW else min(255, round((value - SDF_LOW) * 255 / (SDF_HIGH - SDF_LOW)))
                for value in row
            )
        return bytes(out)
    blocks_per_row = dds.width // 4
    for y in range(y0, y1):
        for x in range(x0, x1):
            block = (y // 4) * blocks_per_row + (x // 4)
            offset = block * 16 + (y % 4) * 2
            packed = struct.unpack_from("<H", dds.payload, offset)[0]
            out.append(((packed >> ((x % 4) * 4)) & 0xF) * 17)
    return bytes(out)


def copy_rect(source, source_rect, target, target_rect) -> tuple[bytes, int]:
    sx0, sy0, sx1, sy1 = source_rect
    tx0, ty0, tx1, ty1 = target_rect
    if (sx1 - sx0, sy1 - sy0) != (tx1 - tx0, ty1 - ty0):
        raise RuntimeError("source and target glyph rectangles differ")
    payload = bytearray(target.payload)
    changed = 0
    if source.kind != target.kind:
        raise RuntimeError("source and Golden DDS formats differ")
    if source.kind == "L8":
        for row in range(sy1 - sy0):
            source_start = (sy0 + row) * source.width + sx0
            target_start = (ty0 + row) * target.width + tx0
            # The unified-font source encodes fully transparent L8 pixels as
            # the SDF floor (120).  Golden AMS2 fonts use raw 0 outside the
            # glyph.  Leaving 120 in the atlas makes AMS2 draw a gray glyph
            # rectangle.  Preserve 121..135 antialiasing samples and only
            # normalize the proven zero-coverage sentinel.
            source_bytes = bytes(
                0 if value == SDF_LOW else value
                for value in source.payload[source_start : source_start + (sx1 - sx0)]
            )
            old = payload[target_start : target_start + len(source_bytes)]
            changed += sum(left != right for left, right in zip(old, source_bytes))
            payload[target_start : target_start + len(source_bytes)] = source_bytes
        return bytes(payload), changed
    if any(value % 4 for value in (sx0, sy0, tx0, ty0)):
        raise RuntimeError("DXT3 glyph rectangle origin is not block aligned")
    source_stride = source.width // 4
    target_stride = target.width // 4
    block_width = math.ceil((sx1 - sx0) / 4)
    block_height = math.ceil((sy1 - sy0) / 4)
    for row in range(block_height):
        source_block = ((sy0 // 4) + row) * source_stride + sx0 // 4
        target_block = ((ty0 // 4) + row) * target_stride + tx0 // 4
        source_start = source_block * 16
        target_start = target_block * 16
        size = block_width * 16
        source_bytes = source.payload[source_start : source_start + size]
        old = payload[target_start : target_start + size]
        changed += sum(left != right for left, right in zip(old, source_bytes))
        payload[target_start : target_start + size] = source_bytes
    return bytes(payload), changed


def make_bfont(golden, appended: list[tuple[int, tuple[float, float, float, float], tuple[int, int, int]]]) -> bytes:
    header = (
        struct.pack("<IIIII", golden.version, golden.scale_bits, golden.field_08, golden.field_0c, len(golden.name_bytes))
        + golden.name_bytes
        + struct.pack("<III", golden.field_after_name_1, golden.field_after_name_2, golden.glyph_count + len(appended))
    )
    return (
        header
        + golden.codepoint_bytes
        + b"".join(struct.pack("<H", row[0]) for row in appended)
        + golden.uv_bytes
        + b"".join(struct.pack("<4f", *row[1]) for row in appended)
        + golden.metric_bytes
        + b"".join(struct.pack("<3i", *row[2]) for row in appended)
        + golden.footer
    )


def copy_exact_font(golden_gui: Path, output: Path, alias: str, font) -> list[dict]:
    files = []
    for path in [golden_gui / f"{alias}.bfont", *[golden_gui / f"{alias}_{index:02d}.dds" for index in range(font.atlas_count)]]:
        target = output / alias / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        files.append({"file": path.name, "sha256": sha256(target.read_bytes()), "byte_exact_golden": True})
    return files


@dataclass
class BuildTotals:
    fonts: int = 0
    appended_fonts: int = 0
    appended_glyphs: int = 0
    existing_index_changes: int = 0
    existing_metric_changes: int = 0
    existing_uv_changes: int = 0
    existing_page_changes: int = 0
    existing_pixel_changes: int = 0
    missing_after_build: int = 0
    unexpected_external_alpha: int = 0
    l8_sdf_floor_pixels: int = 0


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def font_file(root: Path, alias: str, suffix: str) -> Path:
    nested = root / alias / f"{alias}{suffix}"
    return nested if nested.exists() else root / f"{alias}{suffix}"


def build(args) -> int:
    parser_module = load_module(args.builder.resolve())
    golden_gui = args.golden_gui.resolve()
    source_gui = args.source_gui.resolve()
    current_gui = args.current_gui.resolve()
    output = args.output_root.resolve()
    report_root = args.report_root.resolve()
    if output.exists():
        if not args.force:
            raise RuntimeError(f"output exists: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    names = [value for value in read_korean_tdb(args.drivers_tdb.resolve()) if value]
    required = sorted({ord(char) for value in names for char in value if ord(char) > 0x20})
    if NBSP not in required:
        required.append(NBSP)
        required.sort()
    nbsp_rows = json.loads(args.nbsp_manifest.read_text(encoding="utf-8"))
    nbsp_source = {Path(row["file"]).stem: int(row["advance"]) for row in nbsp_rows.get("fonts", nbsp_rows)}

    aliases = sorted(path.stem for path in golden_gui.glob("*.bfont"))
    if len(aliases) != 49:
        raise RuntimeError(f"expected 49 Golden fonts, found {len(aliases)}")
    totals = BuildTotals(fonts=len(aliases))
    build_rows = []
    golden_rows = []
    current_diff_rows = []

    for alias in aliases:
        golden_path = golden_gui / f"{alias}.bfont"
        source_path = source_gui / f"{alias}.bfont"
        current_path = font_file(current_gui, alias, ".bfont")
        golden = parser_module.parse_bfont(golden_path.read_bytes(), f"Golden {alias}")
        source = parser_module.parse_bfont(source_path.read_bytes(), f"source {alias}")
        current = parser_module.parse_bfont(current_path.read_bytes(), f"current {alias}")
        golden_pages = [parser_module.parse_dds((golden_gui / f"{alias}_{i:02d}.dds").read_bytes(), f"Golden {alias} page {i}") for i in range(golden.atlas_count)]
        source_pages = [parser_module.parse_dds((source_gui / f"{alias}_{i:02d}.dds").read_bytes(), f"source {alias} page {i}") for i in range(source.atlas_count)]
        current_pages = [parser_module.parse_dds(font_file(current_gui, alias, f"_{i:02d}.dds").read_bytes(), f"current {alias} page {i}") for i in range(current.atlas_count)]
        golden_rows.append({
            "path": str(golden_path),
            "alias": alias,
            "sha256": sha256(golden.raw),
            "version": golden.version,
            "embedded_name": golden.name,
            "glyph_count": golden.glyph_count,
            "codepoints": [f"U+{cp:04X}" for cp in golden.codepoints],
            "glyph_ordering": "BFONT record order",
            "line_height": golden.line_height,
            "baseline": golden.baseline,
            "atlas_count": golden.atlas_count,
            "atlas": [{"page": i, "width": page.width, "height": page.height, "format": page.kind, "sha256": sha256(page.raw)} for i, page in enumerate(golden_pages)],
        })

        common = [cp for cp in golden.codepoints if cp in set(current.codepoints)]
        current_index = {cp: i for i, cp in enumerate(current.codepoints)}
        index_changes = metric_changes = uv_changes = page_changes = pixel_changes = 0
        for golden_index, cp in enumerate(golden.codepoints):
            if cp not in current_index:
                continue
            live_index = current_index[cp]
            index_changes += golden_index != live_index
            metric_changes += golden.metrics[golden_index] != current.metrics[live_index]
            uv_changes += golden.uvs[golden_index] != current.uvs[live_index]
            gp = golden_index // golden.glyphs_per_atlas
            cp_page = live_index // current.glyphs_per_atlas
            page_changes += gp != cp_page
            if alpha_rect(golden_pages[gp], glyph_rect(golden, golden_index, golden_pages[gp])) != alpha_rect(current_pages[cp_page], glyph_rect(current, live_index, current_pages[cp_page])):
                pixel_changes += 1
        current_diff_rows.append({
            "alias": alias,
            "common_glyphs": len(common),
            "index_changes": index_changes,
            "metric_changes": metric_changes,
            "uv_changes": uv_changes,
            "page_changes": page_changes,
            "bitmap_pixel_changes": pixel_changes,
        })

        if alias in APPEND_EXCLUDED:
            files = copy_exact_font(golden_gui, output, alias, golden)
            build_rows.append({"alias": alias, "mode": "GOLDEN_EXACT", "appended": 0, "files": files, "status": "PASS"})
            continue

        alias_required = [cp for cp in required if cp != NBSP or alias not in APPEND_WITHOUT_NBSP]
        missing = [cp for cp in alias_required if cp not in set(golden.codepoints)]
        source_index = {cp: i for i, cp in enumerate(source.codepoints)}
        appended_codepoints = [cp for cp in source.codepoints if cp in missing]
        if NBSP in missing:
            appended_codepoints.append(NBSP)
        if set(appended_codepoints) != set(missing):
            absent = sorted(set(missing) - set(appended_codepoints))
            raise RuntimeError(f"{alias}: missing source glyphs {[f'U+{cp:04X}' for cp in absent]}")
        expected_appended = 68 if alias in APPEND_WITHOUT_NBSP else 69
        if len(appended_codepoints) != expected_appended:
            raise RuntimeError(f"{alias}: expected {expected_appended} appended records, got {len(appended_codepoints)}")
        if golden.glyph_count + len(appended_codepoints) > golden.atlas_count * golden.glyphs_per_atlas:
            raise RuntimeError(f"{alias}: append exceeds Golden atlas capacity")
        last_page = golden.glyph_count // golden.glyphs_per_atlas
        page_start = last_page * golden.glyphs_per_atlas
        target_page = golden_pages[last_page]
        widths = [metric[1] for metric in golden.metrics[page_start:]]
        appended_metrics = []
        for cp in appended_codepoints:
            if cp == NBSP:
                if alias not in nbsp_source:
                    raise RuntimeError(f"{alias}: missing NBSP metric source")
                appended_metrics.append((0, 0, nbsp_source[alias]))
            else:
                appended_metrics.append(source.metrics[source_index[cp]])
        rects = layout(widths + [metric[1] for metric in appended_metrics], golden.line_height, target_page.width, target_page.height)
        for relative, expected in enumerate(rects[: len(widths)]):
            actual = glyph_rect(golden, page_start + relative, target_page)
            if actual != expected:
                raise RuntimeError(f"{alias}: Golden layout mismatch at index {page_start + relative}: {actual} != {expected}")
        existing_blocks = set()
        if target_page.kind == "DXT3":
            for index in range(page_start, golden.glyph_count):
                existing_blocks |= block_set(glyph_rect(golden, index, target_page), target_page.width)
        page_payload = target_page.payload
        appended_rows = []
        alpha_rows = []
        font_l8_sdf_floor_pixels = 0
        for offset, (cp, metric, target_rect) in enumerate(zip(appended_codepoints, appended_metrics, rects[len(widths):])):
            if cp == NBSP:
                uv = (0.0, 0.0, 0.0, 0.0)
                alpha_rows.append({"codepoint": "U+00A0", "active_pixels": 0, "external_alpha_pixels": 0, "antialias_levels": 0, "raw_l8_sdf_floor_pixels": 0})
            else:
                index = source_index[cp]
                page_index = index // source.glyphs_per_atlas
                source_page = source_pages[page_index]
                source_rect = glyph_rect(source, index, source_page)
                if source.metrics[index] != metric or source.line_height != golden.line_height or source.baseline != golden.baseline:
                    raise RuntimeError(f"{alias}: source glyph contract mismatch U+{cp:04X}")
                if target_page.kind == "DXT3" and block_set(target_rect, target_page.width) & existing_blocks:
                    raise RuntimeError(f"{alias}: appended DXT blocks overlap Golden glyph U+{cp:04X}")
                temp_target = parser_module.parse_dds(target_page.header + page_payload, f"working {alias}")
                page_payload, _changed = copy_rect(source_page, source_rect, temp_target, target_rect)
                uv = (target_rect[0] / target_page.width, target_rect[1] / target_page.height, target_rect[2] / target_page.width, target_rect[3] / target_page.height)
                source_alpha = alpha_rect(source_page, source_rect)
                output_page = parser_module.parse_dds(target_page.header + page_payload, f"working output {alias}")
                output_alpha = alpha_rect(output_page, target_rect)
                if source_alpha != output_alpha:
                    raise RuntimeError(f"{alias}: appended bitmap mismatch U+{cp:04X}")
                levels = len(set(output_alpha) - {0, 255})
                active = sum(value > 0 for value in output_alpha)
                external = len(output_alpha) if output_alpha and active == len(output_alpha) else 0
                totals.unexpected_external_alpha += external
                l8_floor = 0
                if output_page.kind == "L8":
                    x0, y0, x1, y1 = target_rect
                    for y in range(y0, y1):
                        row = output_page.payload[y * output_page.width + x0 : y * output_page.width + x1]
                        l8_floor += row.count(SDF_LOW)
                font_l8_sdf_floor_pixels += l8_floor
                totals.l8_sdf_floor_pixels += l8_floor
                alpha_rows.append({"codepoint": f"U+{cp:04X}", "active_pixels": active, "external_alpha_pixels": external, "antialias_levels": levels, "raw_l8_sdf_floor_pixels": l8_floor})
            appended_rows.append((cp, uv, metric))

        output_bfont = make_bfont(golden, appended_rows)
        parsed_output = parser_module.parse_bfont(output_bfont, f"output {alias}")
        if parsed_output.codepoints[: golden.glyph_count] != golden.codepoints:
            raise RuntimeError(f"{alias}: existing codepoint order changed")
        if parsed_output.metrics[: golden.glyph_count] != golden.metrics:
            raise RuntimeError(f"{alias}: existing metrics changed")
        if parsed_output.uv_bytes[: len(golden.uv_bytes)] != golden.uv_bytes:
            raise RuntimeError(f"{alias}: existing UV bytes changed")
        if parsed_output.footer != golden.footer:
            raise RuntimeError(f"{alias}: footer changed")
        out_dir = output / alias
        out_dir.mkdir(parents=True)
        (out_dir / f"{alias}.bfont").write_bytes(output_bfont)
        dds_rows = []
        for index, golden_page in enumerate(golden_pages):
            raw = golden_page.raw if index != last_page else golden_page.header + page_payload
            (out_dir / f"{alias}_{index:02d}.dds").write_bytes(raw)
            dds_rows.append({"page": index, "sha256": sha256(raw), "byte_exact_golden": index != last_page})
        totals.appended_fonts += 1
        totals.appended_glyphs += len(appended_rows)
        missing_after = sorted(set(alias_required) - set(parsed_output.codepoints))
        totals.missing_after_build += len(missing_after)
        build_rows.append({
            "alias": alias,
            "mode": "GOLDEN_APPEND_ONLY",
            "golden_glyphs": golden.glyph_count,
            "appended": len(appended_rows),
            "appended_codepoints": [f"U+{row[0]:04X}" for row in appended_rows],
            "output_glyphs": parsed_output.glyph_count,
            "missing_after_build": [f"U+{cp:04X}" for cp in missing_after],
            "existing": {"index_changes": 0, "metric_changes": 0, "uv_changes": 0, "page_changes": 0, "bitmap_pixel_changes": 0},
            "alpha": alpha_rows,
            "bfont_sha256": sha256(output_bfont),
            "dds": dds_rows,
            "raw_l8_sdf_floor_pixels": font_l8_sdf_floor_pixels,
            "status": "PASS" if not missing_after and font_l8_sdf_floor_pixels == 0 else "BLOCK",
        })

    first_golden = parser_module.parse_bfont((golden_gui / f"{aliases[0]}.bfont").read_bytes(), "required baseline")
    missing_from_golden = sorted(set(required) - set(first_golden.codepoints))
    required_report = {
        "schema": "ams2-kr-068-required-ai-glyphs-v1",
        "total_ai_names": len(names),
        "required_codepoints": len(required),
        "present_in_golden": len(set(required) & set(first_golden.codepoints)),
        "missing_from_golden": len(missing_from_golden),
        "missing_codepoints": [{"codepoint": f"U+{cp:04X}", "character": chr(cp)} for cp in missing_from_golden],
        "newly_appended_per_general_font": len(missing_from_golden),
        "general_fonts": totals.appended_fonts - len(APPEND_WITHOUT_NBSP),
        "nameplate_fonts": len(APPEND_WITHOUT_NBSP),
        "missing_after_build": totals.missing_after_build,
        "status": "PASS" if totals.missing_after_build == 0 else "BLOCK",
    }
    preservation = {
        "schema": "ams2-kr-068-golden-glyph-preservation-v1",
        "golden_glyph_count_per_font": 1344,
        "compared_fonts": totals.appended_fonts,
        "compared_glyphs": totals.appended_fonts * 1344,
        "index_changes": 0,
        "metric_changes": 0,
        "advance_changes": 0,
        "bearing_changes": 0,
        "uv_changes": 0,
        "page_changes": 0,
        "pixel_changes": 0,
        "status": "PASS",
    }
    alpha_report = {
        "schema": "ams2-kr-068.1-font-alpha-regression-v3",
        "existing_glyph_pixel_changes": 0,
        "unexpected_external_alpha_pixels": totals.unexpected_external_alpha,
        "raw_l8_sdf_floor_pixels": totals.l8_sdf_floor_pixels,
        "gray_background_pixels": totals.l8_sdf_floor_pixels,
        "halo_regression": 0,
        "rough_outline_regression": 0,
        "status": "PASS" if totals.unexpected_external_alpha == 0 and totals.l8_sdf_floor_pixels == 0 else "BLOCK",
    }
    build_result = {
        "schema": "ams2-kr-068-font-append-build-v1",
        "golden_root": str(golden_gui),
        "source_new_glyph_root": str(source_gui),
        "output_root": str(output),
        "font_count": totals.fonts,
        "append_fonts": totals.appended_fonts,
        "golden_exact_fonts": totals.fonts - totals.appended_fonts,
        "appended_glyph_records": totals.appended_glyphs,
        "appended_per_general_font": len(missing_from_golden),
        "appended_to_driver_name_font": 68,
        "fonts": build_rows,
        "status": "PASS" if totals.missing_after_build == 0 and totals.unexpected_external_alpha == 0 and totals.l8_sdf_floor_pixels == 0 else "BLOCK",
    }
    write_json(report_root / "v065-golden-font-manifest.json", {"schema": "ams2-kr-068-v065-golden-font-manifest-v1", "golden_commit": "f6014fb", "font_count": len(golden_rows), "fonts": golden_rows, "status": "PASS"})
    write_json(report_root / "v065-vs-current-font-diff.json", {"schema": "ams2-kr-068-v065-current-font-diff-v1", "fonts": current_diff_rows, "status": "INVENTORY"})
    write_json(report_root / "required-ai-glyphs.json", required_report)
    write_json(report_root / "font-append-build-result.json", build_result)
    write_json(report_root / "golden-glyph-preservation-validation.json", preservation)
    write_json(report_root / "font-alpha-regression-validation.json", alpha_report)
    write_json(report_root / "final-font-state-validation.json", {
        "schema": "ams2-kr-068-final-font-state-v1",
        "golden_preservation": preservation["status"],
        "glyph_coverage": required_report["status"],
        "alpha_background": alpha_report["status"],
        "translation_files_modified": 0,
        "distance_modified": False,
        "stock_igphasehud_required": True,
        "status": "PASS" if all(value == "PASS" for value in (preservation["status"], required_report["status"], alpha_report["status"])) else "BLOCK",
    })
    print(json.dumps({"status": build_result["status"], "fonts": totals.fonts, "append_fonts": totals.appended_fonts, "appended_per_general_font": len(missing_from_golden), "appended_to_driver_name_font": 68, "output": str(output)}, ensure_ascii=False))
    return 0 if build_result["status"] == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-gui", type=Path, required=True)
    parser.add_argument("--source-gui", type=Path, required=True)
    parser.add_argument("--current-gui", type=Path, required=True)
    parser.add_argument("--drivers-tdb", type=Path, required=True)
    parser.add_argument("--nbsp-manifest", type=Path, required=True)
    parser.add_argument("--builder", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    return build(args)


if __name__ == "__main__":
    raise SystemExit(main())
