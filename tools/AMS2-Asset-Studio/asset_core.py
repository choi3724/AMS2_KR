#!/usr/bin/env python3
"""Core operations for the AMS2 Font/Layout/Text Studio.

All write operations create a caller-selected output.  This module never edits
the input file or installs files into the game directory.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any

from PIL import Image


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"모듈을 불러올 수 없습니다: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_bgui(path: Path, bgui_tool_path: Path):
    tool = load_module(bgui_tool_path, "ams2_asset_studio_bgui")
    data = path.read_bytes()
    parsed = tool.ParsedBGUI.parse(data, strict_targets=False)
    return tool, parsed


def bgui_rows(path: Path, bgui_tool_path: Path) -> list[dict[str, Any]]:
    _tool, parsed = load_bgui(path, bgui_tool_path)
    return [
        {
            "ordinal": record.ordinal,
            "object_id": record.object_id,
            "text_reference": record.text_reference,
            "text_reference_hash": f"0x{record.text_reference_hash:08X}",
            "font": record.font,
            "x": record.position[0],
            "y": record.position[1],
            "width": record.size[0],
            "height": record.size[1],
            "flags": f"0x{record.flags:08X}",
        }
        for record in parsed.text_records
    ]


def edit_bgui_copy(
    input_path: Path,
    output_path: Path,
    bgui_tool_path: Path,
    edits: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    if input_path.resolve() == output_path.resolve():
        raise RuntimeError("입력 BGUI를 직접 덮어쓸 수 없습니다. 다른 출력 파일을 선택하십시오.")
    if output_path.exists():
        raise RuntimeError(f"출력 파일이 이미 있습니다: {output_path}")
    tool, before = load_bgui(input_path, bgui_tool_path)
    unknown = sorted(set(edits) - set(range(len(before.text_records))))
    if unknown:
        raise RuntimeError(f"존재하지 않는 Text ordinal: {unknown}")

    geometry_data = bytearray(before.data)
    font_replacements: dict[int, str] = {}
    for ordinal, edit in sorted(edits.items()):
        record = before.text_records[ordinal]
        x = float(edit.get("x", record.position[0]))
        y = float(edit.get("y", record.position[1]))
        width = float(edit.get("width", record.size[0]))
        height = float(edit.get("height", record.size[1]))
        if width <= 0 or height <= 0:
            raise RuntimeError(f"Text {ordinal}: 폭과 높이는 0보다 커야 합니다.")
        if not all(math.isfinite(value) and abs(value) <= 1.0e8 for value in (x, y, width, height)):
            raise RuntimeError(f"Text {ordinal}: 좌표/크기가 유효하지 않습니다.")
        struct.pack_into("<4f", geometry_data, record.start + 17, x, y, width, height)
        font = str(edit.get("font", record.font)).strip()
        if font != record.font:
            font_replacements[ordinal] = font

    geometry_parsed = tool.ParsedBGUI.parse(bytes(geometry_data), strict_targets=False)
    output_data = geometry_parsed.serialize_fonts(font_replacements)
    after = tool.ParsedBGUI.parse(output_data, strict_targets=False)
    if len(after.text_records) != len(before.text_records):
        raise RuntimeError("저장 후 Text 레코드 수가 달라졌습니다.")
    for ordinal, edit in sorted(edits.items()):
        old = before.text_records[ordinal]
        new = after.text_records[ordinal]
        expected_geometry = (
            float(edit.get("x", old.position[0])),
            float(edit.get("y", old.position[1])),
            float(edit.get("width", old.size[0])),
            float(edit.get("height", old.size[1])),
        )
        actual_geometry = (*new.position, *new.size)
        if any(abs(left - right) > 0.0001 for left, right in zip(expected_geometry, actual_geometry)):
            raise RuntimeError(f"Text {ordinal}: 저장 후 geometry 검증에 실패했습니다.")
        expected_font = str(edit.get("font", old.font)).strip()
        if new.font != expected_font:
            raise RuntimeError(f"Text {ordinal}: 저장 후 font 검증에 실패했습니다.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_data)
    report = {
        "schema": "ams2-asset-studio-bgui-edit-v1",
        "status": "PASS",
        "input": str(input_path.resolve()),
        "output": str(output_path.resolve()),
        "input_sha256": sha256_bytes(before.data),
        "output_sha256": sha256_bytes(output_data),
        "text_record_count": len(after.text_records),
        "edited_ordinals": sorted(edits),
        "font_route_edits": len(font_replacements),
        "geometry_edits": len(edits),
    }
    write_json(output_path.with_suffix(output_path.suffix + ".edit.json"), report)
    return report


def load_tdb(path: Path, tdb_tool_path: Path):
    tool = load_module(tdb_tool_path, "ams2_asset_studio_tdb")
    return tool, tool.parse_tdb(path)


def tdb_rows(path: Path, tdb_tool_path: Path) -> list[dict[str, Any]]:
    tool, document = load_tdb(path, tdb_tool_path)
    english = document.language("English")
    korean = document.language("Korean")
    rows = []
    for index, key in enumerate(document.keys):
        group = tool.resolve_group(document, key).get("group") or "UNRESOLVED"
        rows.append(
            {
                "index": index,
                "group": group,
                "key": key,
                "hash": f"0x{english.hashes[index]:016X}",
                "english": english.values[index],
                "korean": korean.values[index],
            }
        )
    return rows


def edit_tdb_copy(
    input_path: Path,
    output_path: Path,
    tdb_tool_path: Path,
    korean_edits: dict[int, str],
) -> dict[str, Any]:
    if input_path.resolve() == output_path.resolve():
        raise RuntimeError("입력 TDB를 직접 덮어쓸 수 없습니다. 다른 출력 파일을 선택하십시오.")
    if output_path.exists():
        raise RuntimeError(f"출력 파일이 이미 있습니다: {output_path}")
    tool, before = load_tdb(input_path, tdb_tool_path)
    korean = before.language("Korean")
    unknown = sorted(index for index in korean_edits if index < 0 or index >= before.key_count)
    if unknown:
        raise RuntimeError(f"존재하지 않는 TDB index: {unknown}")
    old_values = list(korean.values)
    for index, value in korean_edits.items():
        korean.values[index] = value
    output_data = tool.serialize_tdb(before)
    after = tool.parse_tdb_bytes(output_data, str(output_path))
    if after.keys != before.keys or after.language("English").values != before.language("English").values:
        raise RuntimeError("저장 후 key 또는 English block이 변경되었습니다.")
    for language in before.languages:
        if language.name == "Korean":
            continue
        if after.language(language.name).values != language.values:
            raise RuntimeError(f"저장 후 {language.name} block이 변경되었습니다.")
    for index, value in korean_edits.items():
        if after.language("Korean").values[index] != value:
            raise RuntimeError(f"TDB index {index}: 저장 후 Korean 값 검증 실패")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_data)
    changed = [index for index in sorted(korean_edits) if old_values[index] != korean_edits[index]]
    report = {
        "schema": "ams2-asset-studio-tdb-edit-v1",
        "status": "PASS",
        "input": str(input_path.resolve()),
        "output": str(output_path.resolve()),
        "input_sha256": sha256_file(input_path),
        "output_sha256": sha256_bytes(output_data),
        "key_count": before.key_count,
        "requested_edit_count": len(korean_edits),
        "changed_index_count": len(changed),
        "changed_indices": changed,
    }
    write_json(output_path.with_suffix(output_path.suffix + ".edit.json"), report)
    return report


def _scale_glyph(glyph, glyph_class, scale_x: float, scale_y: float, offset_x: int, offset_y: int):
    if glyph.mask.width and glyph.mask.height:
        width = max(1, int(math.floor(glyph.mask.width * scale_x + 0.5)))
        height = max(1, int(math.floor(glyph.mask.height * scale_y + 0.5)))
        mask = glyph.mask.resize((width, height), Image.Resampling.LANCZOS)
    else:
        mask = glyph.mask
    return glyph_class(
        mask,
        int(math.floor(glyph.left * scale_x + 0.5)) + offset_x,
        int(math.floor(glyph.top * scale_y + 0.5)) + offset_y,
        max(0, int(math.floor(glyph.advance * scale_x + 0.5))),
        f"{glyph.source}_SCALED",
    )


def build_single_font(
    source_font: Path,
    base_bfont: Path,
    template_dds: Path,
    output_dir: Path,
    alias: str,
    pixel_size: int,
    scale_x: float,
    scale_y: float,
    offset_x: int,
    offset_y: int,
    line_height: int,
    baseline: int,
    extra_characters: str,
    unified_builder_path: Path,
    dds_builder_path: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise RuntimeError(f"출력 폴더가 이미 있습니다: {output_dir}")
    if not alias or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in alias):
        raise RuntimeError("폰트 alias는 영문, 숫자, _, -만 사용할 수 있습니다.")
    if pixel_size < 8 or pixel_size > 256:
        raise RuntimeError("픽셀 크기는 8~256 범위여야 합니다.")
    if not (0.2 <= scale_x <= 4.0 and 0.2 <= scale_y <= 4.0):
        raise RuntimeError("가로/세로 배율은 0.2~4.0 범위여야 합니다.")

    unified = load_module(unified_builder_path, "ams2_asset_studio_unified_font")
    dds_builder = load_module(dds_builder_path, "ams2_asset_studio_dds_builder")
    base = unified.parse_base_font(base_bfont)
    base_metrics = dict(zip(base.codepoints, unified.parse_builder_metrics(base_bfont)))
    requested = tuple(sorted({*base.codepoints, *(ord(character) for character in extra_characters)} - {0x20}))
    if any(value > 0xFFFF for value in requested):
        raise RuntimeError("BFONT codepoint table은 U+FFFF를 초과하는 문자를 지원하지 않습니다.")
    cmap = unified.parse_cmap(source_font)
    missing = [
        value
        for value in requested
        if value not in cmap
        and value not in (0x2154, 0x24D2)
        and not (value in base_metrics and base_metrics[value][1] == 0)
    ]
    if missing:
        preview = " ".join(f"U+{value:04X}({chr(value)})" for value in missing[:20])
        raise RuntimeError(f"원본 폰트에 필요한 글리프가 없습니다: {preview}")

    font = unified.ImageFont.truetype(str(source_font), pixel_size)
    glyphs = []
    for value in requested:
        if value in base_metrics and base_metrics[value][1] == 0:
            glyph = unified.Glyph(Image.new("L", (0, 0), 0), base_metrics[value][0], 0, base_metrics[value][2], "BASE_EMPTY_SENTINEL")
        elif value in cmap:
            glyph = unified.direct_glyph(font, value)
        else:
            glyph = unified.composed_glyph(font, value)
        glyphs.append(_scale_glyph(glyph, unified.Glyph, scale_x, scale_y, offset_x, offset_y))

    ascent, descent = font.getmetrics()
    top = min([-ascent, *(glyph.top for glyph in glyphs if glyph.mask.height)])
    bottom = max([descent, *(glyph.top + glyph.mask.height for glyph in glyphs if glyph.mask.height)])
    requested_line_height = line_height if line_height > 0 else base.line_height
    actual_height = bottom - top
    final_line_height = max(requested_line_height, actual_height)
    if baseline < 0:
        minimum_baseline = -top
        maximum_baseline = final_line_height - bottom
        if minimum_baseline > maximum_baseline:
            final_line_height += minimum_baseline - maximum_baseline
            maximum_baseline = final_line_height - bottom
        final_baseline = min(max(base.baseline, minimum_baseline), maximum_baseline)
    else:
        final_baseline = baseline
    if final_baseline + top < 0 or final_baseline + bottom > final_line_height:
        raise RuntimeError("지정한 line height/baseline 안에 글리프가 들어가지 않습니다.")

    template = dds_builder.parse_dds(template_dds.read_bytes(), str(template_dds))
    width, height = unified.select_dimensions([glyph.mask.width for glyph in glyphs], final_line_height)
    pages, uvs = unified.render_pages(
        dds_builder, template, requested, glyphs, final_line_height, final_baseline, width, height
    )
    output_base = dataclasses.replace(base, name=alias)
    bfont_data = unified.build_bfont(
        output_base, requested, uvs, glyphs, final_line_height, final_baseline, len(pages)
    )
    reparsed = dds_builder.parse_bfont(bfont_data, alias)
    expected_metrics = tuple((glyph.left, glyph.mask.width, glyph.advance) for glyph in glyphs)
    if reparsed.codepoints != requested or reparsed.metrics != expected_metrics:
        raise RuntimeError("생성 BFONT round-trip 검증에 실패했습니다.")

    output_dir.mkdir(parents=True)
    bfont_path = output_dir / f"{alias}.bfont"
    bfont_path.write_bytes(bfont_data)
    dds_rows = []
    for index, page in enumerate(pages):
        path = output_dir / f"{alias}_{index:02d}.dds"
        path.write_bytes(page)
        dds_rows.append({"file": path.name, "bytes": len(page), "sha256": sha256_bytes(page)})
    manifest = {
        "schema": "ams2-asset-studio-single-font-build-v1",
        "status": "PASS",
        "source_font": str(source_font.resolve()),
        "source_font_sha256": sha256_file(source_font),
        "base_bfont": str(base_bfont.resolve()),
        "base_bfont_sha256": sha256_file(base_bfont),
        "template_dds": str(template_dds.resolve()),
        "template_dds_sha256": sha256_file(template_dds),
        "alias": alias,
        "pixel_size": pixel_size,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "line_height": final_line_height,
        "baseline": final_baseline,
        "glyph_count": len(requested),
        "atlas": {"count": len(pages), "width": width, "height": height, "format": template.kind},
        "bfont": {"file": bfont_path.name, "bytes": len(bfont_data), "sha256": sha256_bytes(bfont_data)},
        "dds": dds_rows,
        "checks": {"missing_glyphs": False, "roundtrip": True, "input_untouched": True},
    }
    write_json(output_dir / "font-build-manifest.json", manifest)
    return manifest
