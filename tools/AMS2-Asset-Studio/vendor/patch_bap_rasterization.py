#!/usr/bin/env python3
"""Re-rasterize only U+BC25 for the two AMS2 driver-name font routes.

The source is always the declared Pretendard TTF.  No bitmap is hand-edited:
the glyph is rendered at 2x through Pillow/FreeType, reduced to the existing
1x bitmap bounds with BOX filtering, and encoded with the established AMS2 L8
coverage contract.  BFONT bytes, metrics, UVs, every other glyph, and every
DDS byte outside the two U+BC25 rectangles must remain byte-exact.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features


TARGET = ord("밥")
SDF_LOW = 120
SDF_HIGH = 136
ROUTES = {
    "kr13_phoenix_body_large": {
        "weight": "Medium",
        "pixel_size": 14,
        "expected_bfont_sha256": "C8B4A5C7784FDB29D94E08237635802A650316BD340A462478A048055E523C7E",
        "expected_dds_sha256": "4133F425F7D16EB5524EA0144761C1E2E3CEB3A7787AE3DC4998D2E84E1610A2",
    },
    "kr13_driver_name_semibold": {
        "weight": "SemiBold",
        "pixel_size": 20,
        "expected_bfont_sha256": "A4005F7BFE733C40029C231CFA6090C469FD4F45EC83DAE03916BB9EBBDEA0C6",
        "expected_dds_sha256": "6D0F1BD5BFFD1FEC50F1E4948CCC34E99DC94D900D83407C8AB9A6AD387C9767",
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("ams2_bap_patch_parser", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import parser: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def font_file(root: Path, alias: str, suffix: str) -> Path:
    nested = root / alias / f"{alias}{suffix}"
    return nested if nested.exists() else root / f"{alias}{suffix}"


def direct_glyph(font: ImageFont.FreeTypeFont, codepoint: int):
    character = chr(codepoint)
    left, top, right, bottom = font.getbbox(character, anchor="ls")
    mask = Image.new("L", (max(0, right - left), max(0, bottom - top)), 0)
    if mask.width and mask.height:
        ImageDraw.Draw(mask).text(
            (-left, -top), character, font=font, fill=255, anchor="ls"
        )
    advance = int(math.floor(font.getlength(character) + 0.5))
    return mask, (left, top, advance)


def render_2x_box_cell(
    font_path: Path,
    pixel_size: int,
    width: int,
    line_height: int,
    baseline: int,
) -> np.ndarray:
    base_font = ImageFont.truetype(str(font_path), pixel_size)
    base_mask, (_left, top, _advance) = direct_glyph(base_font, TARGET)
    if base_mask.width != width:
        raise RuntimeError(
            f"U+BC25 base width {base_mask.width} != BFONT metric width {width}"
        )
    high_font = ImageFont.truetype(str(font_path), pixel_size * 2)
    high_mask, _metric = direct_glyph(high_font, TARGET)
    reduced = high_mask.resize(base_mask.size, Image.Resampling.BOX)
    cell = Image.new("L", (width, line_height), 0)
    y = baseline + top
    if y < 0 or y + reduced.height > line_height:
        raise RuntimeError("U+BC25 raster exceeds existing line cell")
    cell.paste(reduced, (0, y))
    return np.asarray(cell, dtype=np.uint8)


def encode_l8_coverage(alpha: np.ndarray) -> np.ndarray:
    encoded = np.rint(
        SDF_LOW + alpha.astype(np.float32) * (SDF_HIGH - SDF_LOW) / 255.0
    ).astype(np.uint8)
    return np.where(encoded <= SDF_LOW, 0, encoded).astype(np.uint8)


def decode_l8_coverage(field: np.ndarray) -> np.ndarray:
    return np.where(
        field <= SDF_LOW,
        0,
        np.rint(
            (field.astype(np.float32) - SDF_LOW)
            * 255.0
            / (SDF_HIGH - SDF_LOW)
        ),
    ).clip(0, 255).astype(np.uint8)


def rect_for(font, dds, index: int) -> tuple[int, int, int, int]:
    u0, v0, u1, v1 = font.uvs[index]
    return (
        round(u0 * dds.width),
        round(v0 * dds.height),
        round(u1 * dds.width),
        round(v1 * dds.height),
    )


def inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_path(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def patch_route(parser_module, root: Path, font_root: Path, alias: str, config: dict):
    bfont_path = font_file(root, alias, ".bfont")
    if sha256_path(bfont_path) != config["expected_bfont_sha256"]:
        raise RuntimeError(f"{alias}: unexpected BFONT baseline")
    font = parser_module.parse_bfont(bfont_path.read_bytes(), str(bfont_path))
    index = font.codepoints.index(TARGET)
    page_index = index // font.glyphs_per_atlas
    dds_path = font_file(root, alias, f"_{page_index:02d}.dds")
    before_raw = dds_path.read_bytes()
    if sha256_bytes(before_raw) != config["expected_dds_sha256"]:
        raise RuntimeError(f"{alias}: unexpected target DDS baseline")
    dds = parser_module.parse_dds(before_raw, str(dds_path))
    if dds.kind != "L8":
        raise RuntimeError(f"{alias}: target page is not L8")

    x0, y0, x1, y1 = rect_for(font, dds, index)
    metric = tuple(font.metrics[index])
    if (x1 - x0, y1 - y0) != (metric[1], font.line_height):
        raise RuntimeError(f"{alias}: U+BC25 rect/metric mismatch")
    font_path = font_root / f"Pretendard-{config['weight']}.ttf"
    if not font_path.is_file():
        raise RuntimeError(f"missing source font: {font_path}")
    alpha = render_2x_box_cell(
        font_path,
        config["pixel_size"],
        metric[1],
        font.line_height,
        font.baseline,
    )
    encoded = encode_l8_coverage(alpha)
    if np.any(encoded == SDF_LOW):
        raise RuntimeError(f"{alias}: encoded target contains forbidden raw 120")

    payload = bytearray(dds.payload)
    for row in range(y1 - y0):
        start = (y0 + row) * dds.width + x0
        payload[start : start + (x1 - x0)] = encoded[row].tobytes()
    after_raw = parser_module.make_dds(dds, dds.width, dds.height, bytes(payload))
    changed = [
        offset for offset, (before, after) in enumerate(zip(before_raw, after_raw))
        if before != after
    ]
    allowed = {
        128 + y * dds.width + x
        for y in range(y0, y1)
        for x in range(x0, x1)
    }
    if not changed or any(offset not in allowed for offset in changed):
        raise RuntimeError(f"{alias}: change escaped U+BC25 rectangle or was empty")

    dds_path.write_bytes(after_raw)
    reparsed = parser_module.parse_dds(dds_path.read_bytes(), str(dds_path))
    stored = np.asarray(
        [
            value
            for y in range(y0, y1)
            for value in reparsed.payload[y * reparsed.width + x0 : y * reparsed.width + x1]
        ],
        dtype=np.uint8,
    ).reshape(y1 - y0, x1 - x0)
    expected_visible = decode_l8_coverage(encoded)
    if not np.array_equal(decode_l8_coverage(stored), expected_visible):
        raise RuntimeError(f"{alias}: stored U+BC25 does not round-trip")
    if sha256_path(bfont_path) != config["expected_bfont_sha256"]:
        raise RuntimeError(f"{alias}: BFONT changed")

    return {
        "alias": alias,
        "codepoint": "U+BC25",
        "character": chr(TARGET),
        "source_font": str(font_path),
        "source_font_sha256": sha256_path(font_path),
        "weight": config["weight"],
        "pixel_size": config["pixel_size"],
        "freetype_version": features.version_module("freetype2"),
        "rasterization": "2x Pillow/FreeType grayscale -> BOX downsample -> AMS2 L8 120..136",
        "bfont": str(bfont_path),
        "bfont_sha256": sha256_path(bfont_path),
        "dds": str(dds_path),
        "page": page_index,
        "rect": [x0, y0, x1, y1],
        "uv": list(font.uvs[index]),
        "metric": list(metric),
        "line_height": font.line_height,
        "baseline": font.baseline,
        "before_dds_sha256": sha256_bytes(before_raw),
        "after_dds_sha256": sha256_bytes(after_raw),
        "changed_bytes": len(changed),
        "outside_target_changed_bytes": 0,
        "raw_120_count": int(np.count_nonzero(stored == SDF_LOW)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--font-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise RuntimeError(f"output already exists: {output_root}")
    parser_module = load_module(args.parser.resolve())
    before_inventory = inventory(input_root)
    shutil.copytree(input_root, output_root)
    rows = [
        patch_route(
            parser_module,
            output_root,
            args.font_root.resolve(),
            alias,
            config,
        )
        for alias, config in ROUTES.items()
    ]
    after_inventory = inventory(output_root)
    changed_files = sorted(
        path for path in before_inventory if before_inventory[path] != after_inventory[path]
    )
    expected_changed = sorted(
        Path(row["dds"]).relative_to(output_root).as_posix() for row in rows
    )
    if changed_files != expected_changed:
        raise RuntimeError(
            f"unexpected changed files: actual={changed_files}, expected={expected_changed}"
        )
    if set(before_inventory) != set(after_inventory):
        raise RuntimeError("candidate file set changed")

    report = {
        "schema": "ams2-kr-068.1-bap-raster-micro-patch-v1",
        "status": "PASS",
        "input_root": str(input_root),
        "output_root": str(output_root),
        "target": {"codepoint": "U+BC25", "character": chr(TARGET)},
        "changed_files": changed_files,
        "unchanged_file_count": len(before_inventory) - len(changed_files),
        "routes": rows,
        "contracts": {
            "bfont_changed": 0,
            "uv_metric_changed": 0,
            "non_target_dds_region_changed": 0,
            "other_glyph_changed": 0,
            "manual_bitmap_edit": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
