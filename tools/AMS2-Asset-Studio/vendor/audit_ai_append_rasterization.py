#!/usr/bin/env python3
"""Compare AI append glyphs from Pretendard through source and final AMS2 atlases.

This is a read-only audit.  It renders the same character directly through
Pillow/FreeType, extracts its shader-visible bitmap from the source BFONT/DDS,
and extracts the appended candidate bitmap.  It never edits BFONT or DDS data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, features


SDF_LOW = 120
SDF_HIGH = 136
PLAYER_LIST_ALIAS = "kr13_phoenix_body_large"
NAMEPLATE_ALIAS = "kr13_driver_name_semibold"
TARGET = ord("밥")
# U+BC27 (밧) is not present in the v0.6.5 Golden/source corpus, so the four
# available requested peers are used for byte-level atlas comparison.
COMPARISONS = tuple(map(ord, "밤법바브"))


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("ams2_ai_append_audit_parser", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import parser: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def font_file(root: Path, alias: str, suffix: str) -> Path:
    nested = root / alias / f"{alias}{suffix}"
    return nested if nested.exists() else root / f"{alias}{suffix}"


def glyph_rect(font, index: int, dds) -> tuple[int, int, int, int]:
    uv = font.uvs[index]
    return (
        round(uv[0] * dds.width),
        round(uv[1] * dds.height),
        round(uv[2] * dds.width),
        round(uv[3] * dds.height),
    )


def alpha_rect(dds, rect: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = rect
    if x0 == x1:
        return np.zeros((y1 - y0, 0), dtype=np.uint8)
    values: list[int] = []
    if dds.kind == "L8":
        for y in range(y0, y1):
            for value in dds.payload[y * dds.width + x0 : y * dds.width + x1]:
                values.append(
                    0
                    if value <= SDF_LOW
                    else min(255, round((value - SDF_LOW) * 255 / (SDF_HIGH - SDF_LOW)))
                )
    else:
        import struct

        blocks_per_row = dds.width // 4
        for y in range(y0, y1):
            for x in range(x0, x1):
                block = (y // 4) * blocks_per_row + (x // 4)
                offset = block * 16 + (y % 4) * 2
                packed = struct.unpack_from("<H", dds.payload, offset)[0]
                values.append(((packed >> ((x % 4) * 4)) & 0xF) * 17)
    return np.asarray(values, dtype=np.uint8).reshape(y1 - y0, x1 - x0)


def direct_glyph(font: ImageFont.FreeTypeFont, codepoint: int):
    char = chr(codepoint)
    left, top, right, bottom = font.getbbox(char, anchor="ls")
    mask = Image.new("L", (max(0, right - left), max(0, bottom - top)), 0)
    if mask.width and mask.height:
        ImageDraw.Draw(mask).text((-left, -top), char, font=font, fill=255, anchor="ls")
    advance = int(math.floor(font.getlength(char) + 0.5))
    return mask, (left, top, advance)


def quantize(values: np.ndarray, kind: str) -> np.ndarray:
    if kind == "L8":
        field = np.rint(
            SDF_LOW + values.astype(np.float32) * (SDF_HIGH - SDF_LOW) / 255.0
        ).astype(np.uint8)
        return np.where(
            field <= SDF_LOW,
            0,
            np.rint((field.astype(np.float32) - SDF_LOW) * 255.0 / (SDF_HIGH - SDF_LOW)),
        ).clip(0, 255).astype(np.uint8)
    return ((values.astype(np.uint16) * 15 + 127) // 255 * 17).astype(np.uint8)


def direct_cell(
    font: ImageFont.FreeTypeFont,
    codepoint: int,
    line_height: int,
    baseline: int,
    width: int,
    kind: str,
) -> tuple[np.ndarray, tuple[int, int, int], tuple[int, int, int, int]]:
    mask, (left, top, advance) = direct_glyph(font, codepoint)
    if mask.width != width:
        raise RuntimeError(
            f"U+{codepoint:04X}: direct width {mask.width} != BFONT width {width}"
        )
    cell = Image.new("L", (width, line_height), 0)
    paste_y = baseline + top
    if paste_y < 0 or paste_y + mask.height > line_height:
        raise RuntimeError(f"U+{codepoint:04X}: direct bitmap exceeds line cell")
    cell.paste(mask, (0, paste_y))
    return quantize(np.asarray(cell, dtype=np.uint8), kind), (left, width, advance), (0, paste_y, width, paste_y + mask.height)


def oversampled_cell(
    font_path: Path,
    pixel_size: int,
    codepoint: int,
    line_height: int,
    baseline: int,
    width: int,
    kind: str,
    scale: int,
    resample: Image.Resampling = Image.Resampling.LANCZOS,
) -> np.ndarray:
    base_font = ImageFont.truetype(str(font_path), pixel_size)
    base_mask, (_left, top, _advance) = direct_glyph(base_font, codepoint)
    high_font = ImageFont.truetype(str(font_path), pixel_size * scale)
    high_mask, _high_metric = direct_glyph(high_font, codepoint)
    resized = high_mask.resize(base_mask.size, resample)
    cell = Image.new("L", (width, line_height), 0)
    paste_y = baseline + top
    cell.paste(resized, (0, paste_y))
    return quantize(np.asarray(cell, dtype=np.uint8), kind)


def shifted_up_cell(values: np.ndarray) -> np.ndarray:
    shifted = np.zeros_like(values)
    shifted[:-1, :] = values[1:, :]
    return shifted


def plus_one_size_cell(
    font_path: Path,
    pixel_size: int,
    codepoint: int,
    line_height: int,
    baseline: int,
    width: int,
    kind: str,
) -> np.ndarray:
    font = ImageFont.truetype(str(font_path), pixel_size + 1)
    mask, (_left, top, _advance) = direct_glyph(font, codepoint)
    if mask.width != width:
        mask = mask.resize((width, mask.height), Image.Resampling.LANCZOS)
    cell = Image.new("L", (width, line_height), 0)
    paste_y = baseline + top
    if paste_y < 0 or paste_y + mask.height > line_height:
        raise RuntimeError(f"U+{codepoint:04X}: +1px bitmap exceeds line cell")
    cell.paste(mask, (0, paste_y))
    return quantize(np.asarray(cell, dtype=np.uint8), kind)


def bounds_and_padding(values: np.ndarray) -> dict:
    ys, xs = np.nonzero(values)
    height, width = values.shape
    if not len(xs):
        return {
            "active_bounds": None,
            "padding": {"left": width, "right": width, "top": height, "bottom": height},
            "active_pixels": 0,
            "antialias_levels": 0,
        }
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    return {
        "active_bounds": [x0, y0, x1, y1],
        "padding": {"left": x0, "right": width - x1, "top": y0, "bottom": height - y1},
        "active_pixels": int(np.count_nonzero(values)),
        "antialias_levels": len(set(map(int, np.unique(values))) - {0, 255}),
    }


def image_from_alpha(alpha: np.ndarray, scale: int = 12) -> Image.Image:
    height, width = alpha.shape
    rgb = Image.new("RGB", (max(1, width), max(1, height)), (34, 34, 34))
    white = Image.new("RGB", rgb.size, "white")
    rgb.paste(white, mask=Image.fromarray(alpha, mode="L"))
    return rgb.resize((max(1, width * scale), max(1, height * scale)), Image.Resampling.NEAREST)


def save_labeled_grid(path: Path, columns: list[tuple[str, Image.Image]]) -> None:
    label_height = 24
    gap = 10
    width = sum(image.width for _label, image in columns) + gap * (len(columns) - 1)
    height = label_height + max(image.height for _label, image in columns)
    canvas = Image.new("RGB", (width, height), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    x = 0
    for label, image in columns:
        draw.text((x + 2, 4), label, fill="white")
        canvas.paste(image, (x, label_height))
        x += image.width + gap
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def compose_phrase(font, pages, phrase: str, target_override: np.ndarray | None = None) -> np.ndarray:
    records = []
    width = 0
    for character in phrase:
        if ord(character) not in font.codepoints:
            width += max(2, font.line_height // 4)
            continue
        glyph = glyph_data(font, pages, ord(character))
        alpha = target_override if ord(character) == TARGET and target_override is not None else glyph["alpha"]
        records.append((width, alpha))
        width += max(1, int(glyph["metric"][2]))
    canvas = np.zeros((font.line_height, max(1, width)), dtype=np.uint8)
    for x, alpha in records:
        copy_width = min(alpha.shape[1], canvas.shape[1] - x)
        if copy_width > 0:
            canvas[:, x : x + copy_width] = np.maximum(
                canvas[:, x : x + copy_width], alpha[:, :copy_width]
            )
    return canvas


def load_font_assets(parser_module, root: Path, alias: str):
    bfont_path = font_file(root, alias, ".bfont")
    font = parser_module.parse_bfont(bfont_path.read_bytes(), str(bfont_path))
    pages = []
    for page in range(font.atlas_count):
        dds_path = font_file(root, alias, f"_{page:02d}.dds")
        pages.append(parser_module.parse_dds(dds_path.read_bytes(), str(dds_path)))
    return bfont_path, font, pages


def glyph_data(font, pages, codepoint: int) -> dict:
    index = font.codepoints.index(codepoint)
    page_index = index // font.glyphs_per_atlas
    rect = glyph_rect(font, index, pages[page_index])
    alpha = alpha_rect(pages[page_index], rect)
    return {
        "index": index,
        "page": page_index,
        "rect": rect,
        "uv": list(font.uvs[index]),
        "metric": tuple(font.metrics[index]),
        "alpha": alpha,
        "analysis": bounds_and_padding(alpha),
    }


def infer_direct_font(source_font, source_pages, codepoints, source_paths, requested_weight, requested_size):
    path = source_paths[requested_weight]
    for size in range(requested_size, 7, -1):
        font = ImageFont.truetype(str(path), size)
        matches = True
        for codepoint in codepoints[: min(8, len(codepoints))]:
            source = glyph_data(source_font, source_pages, codepoint)
            _mask, metric = direct_glyph(font, codepoint)
            expected = (metric[0], _mask.width, metric[2])
            if expected != source["metric"]:
                matches = False
                break
        if matches:
            return path, font, size
    raise RuntimeError(f"cannot infer direct raster source for {source_font.name}")


def audit_alias(
    parser_module,
    alias: str,
    source_root: Path,
    candidate_root: Path,
    source_paths: dict[str, Path],
    weight: str,
    requested_size: int,
    codepoints: list[int],
):
    source_path, source_font, source_pages = load_font_assets(parser_module, source_root, alias)
    candidate_path, candidate_font, candidate_pages = load_font_assets(parser_module, candidate_root, alias)
    ttf_path, direct_font, actual_size = infer_direct_font(
        source_font, source_pages, codepoints, source_paths, weight, requested_size
    )
    rows = []
    images = {}
    for codepoint in codepoints:
        source = glyph_data(source_font, source_pages, codepoint)
        candidate = glyph_data(candidate_font, candidate_pages, codepoint)
        direct, direct_metric, direct_bitmap_bounds = direct_cell(
            direct_font,
            codepoint,
            source_font.line_height,
            source_font.baseline,
            source["metric"][1],
            source_pages[source["page"]].kind,
        )
        if direct.shape != source["alpha"].shape:
            raise RuntimeError(f"{alias} U+{codepoint:04X}: direct/source shape mismatch")
        direct_delta = np.abs(direct.astype(np.int16) - source["alpha"].astype(np.int16))
        candidate_delta = np.abs(candidate["alpha"].astype(np.int16) - source["alpha"].astype(np.int16))
        oversampled = oversampled_cell(
            ttf_path,
            actual_size,
            codepoint,
            source_font.line_height,
            source_font.baseline,
            source["metric"][1],
            source_pages[source["page"]].kind,
            4,
        )
        oversampled_delta = np.abs(oversampled.astype(np.int16) - direct.astype(np.int16))
        oversampled_2x_box = oversampled_cell(
            ttf_path,
            actual_size,
            codepoint,
            source_font.line_height,
            source_font.baseline,
            source["metric"][1],
            source_pages[source["page"]].kind,
            2,
            Image.Resampling.BOX,
        )
        oversampled_2x_box_delta = np.abs(
            oversampled_2x_box.astype(np.int16) - direct.astype(np.int16)
        )
        rows.append(
            {
                "codepoint": f"U+{codepoint:04X}",
                "character": chr(codepoint),
                "source": {key: value for key, value in source.items() if key != "alpha"},
                "candidate": {key: value for key, value in candidate.items() if key != "alpha"},
                "direct": {
                    "metric": direct_metric,
                    "bitmap_bounds_in_cell": direct_bitmap_bounds,
                    "analysis": bounds_and_padding(direct),
                },
                "direct_vs_source": {
                    "different_pixels": int(np.count_nonzero(direct_delta)),
                    "maximum_delta": int(direct_delta.max(initial=0)),
                    "mean_delta": float(direct_delta.mean()),
                },
                "source_vs_candidate": {
                    "different_pixels": int(np.count_nonzero(candidate_delta)),
                    "maximum_delta": int(candidate_delta.max(initial=0)),
                    "mean_delta": float(candidate_delta.mean()),
                },
                "current_vs_oversampled_4x": {
                    "different_pixels": int(np.count_nonzero(oversampled_delta)),
                    "maximum_delta": int(oversampled_delta.max(initial=0)),
                    "mean_delta": float(oversampled_delta.mean()),
                },
                "current_vs_oversampled_2x_box": {
                    "different_pixels": int(np.count_nonzero(oversampled_2x_box_delta)),
                    "maximum_delta": int(oversampled_2x_box_delta.max(initial=0)),
                    "mean_delta": float(oversampled_2x_box_delta.mean()),
                },
            }
        )
    for codepoint in (TARGET, *COMPARISONS):
        source = glyph_data(source_font, source_pages, codepoint)
        candidate = glyph_data(candidate_font, candidate_pages, codepoint)
        direct, _direct_metric, _direct_bitmap_bounds = direct_cell(
            direct_font,
            codepoint,
            source_font.line_height,
            source_font.baseline,
            source["metric"][1],
            source_pages[source["page"]].kind,
        )
        images[codepoint] = {
            "direct": image_from_alpha(direct),
            "source": image_from_alpha(source["alpha"]),
            "candidate": image_from_alpha(candidate["alpha"]),
            "oversampled4x": image_from_alpha(
                oversampled_cell(
                    ttf_path,
                    actual_size,
                    codepoint,
                    source_font.line_height,
                    source_font.baseline,
                    source["metric"][1],
                    source_pages[source["page"]].kind,
                    4,
                )
            ),
            "oversampled2xBox": image_from_alpha(
                oversampled_cell(
                    ttf_path,
                    actual_size,
                    codepoint,
                    source_font.line_height,
                    source_font.baseline,
                    source["metric"][1],
                    source_pages[source["page"]].kind,
                    2,
                    Image.Resampling.BOX,
                )
            ),
            "oversampled3xBox": image_from_alpha(
                oversampled_cell(
                    ttf_path,
                    actual_size,
                    codepoint,
                    source_font.line_height,
                    source_font.baseline,
                    source["metric"][1],
                    source_pages[source["page"]].kind,
                    3,
                    Image.Resampling.BOX,
                )
            ),
            "oversampled2xLanczos": image_from_alpha(
                oversampled_cell(
                    ttf_path,
                    actual_size,
                    codepoint,
                    source_font.line_height,
                    source_font.baseline,
                    source["metric"][1],
                    source_pages[source["page"]].kind,
                    2,
                    Image.Resampling.LANCZOS,
                )
            ),
            "shiftedUp1": image_from_alpha(shifted_up_cell(direct)),
            "plus1pxFit": image_from_alpha(
                plus_one_size_cell(
                    ttf_path,
                    actual_size,
                    codepoint,
                    source_font.line_height,
                    source_font.baseline,
                    source["metric"][1],
                    source_pages[source["page"]].kind,
                )
            ),
        }
    return {
        "alias": alias,
        "source_bfont": str(source_path),
        "source_bfont_sha256": sha256_path(source_path),
        "candidate_bfont": str(candidate_path),
        "candidate_bfont_sha256": sha256_path(candidate_path),
        "source_font": str(ttf_path),
        "source_font_sha256": sha256_path(ttf_path),
        "weight": weight,
        "requested_px_size": requested_size,
        "actual_px_size": actual_size,
        "line_height": source_font.line_height,
        "baseline": source_font.baseline,
        "atlas_format": source_pages[0].kind,
        "rasterization": {
            "api": "Pillow ImageFont.truetype + getbbox/getlength + ImageDraw.text",
            "script_explicit_freetype_load_flags": "none",
            "effective_hinting": "Pillow/FreeType default hinting",
            "render_mode": "8-bit grayscale antialiasing (L)",
            "oversampling": 1,
            "glyph_scale": 1.0,
            "bitmap_resize": False,
            "padding": "atlas layout gutter 8px; glyph record is width x line_height",
        },
        "rows": rows,
        "images": images,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--required-json", type=Path, required=True)
    parser.add_argument("--font-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    parser_module = load_module(args.parser.resolve())
    source_root = args.source_root.resolve()
    candidate_root = args.candidate_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    required_data = json.loads(args.required_json.read_text(encoding="utf-8"))
    new_codepoints = [
        int(row["codepoint"][2:], 16)
        for row in required_data["missing_codepoints"]
        if row["codepoint"] != "U+00A0"
    ]
    if len(new_codepoints) != 68 or TARGET not in new_codepoints:
        raise RuntimeError(f"expected 68 new AI glyphs including U+BC25, got {len(new_codepoints)}")

    source_paths = {
        weight: next(
            path
            for path in (
                args.font_root.resolve() / f"Pretendard-{weight}.ttf",
                args.font_root.resolve() / f"Pretendard-{weight}.otf",
            )
            if path.is_file()
        )
        for weight in ("Medium", "SemiBold")
    }
    audits = [
        audit_alias(
            parser_module,
            PLAYER_LIST_ALIAS,
            source_root,
            candidate_root,
            source_paths,
            "Medium",
            22,
            new_codepoints,
        ),
        audit_alias(
            parser_module,
            NAMEPLATE_ALIAS,
            source_root,
            candidate_root,
            source_paths,
            "SemiBold",
            20,
            new_codepoints,
        ),
    ]

    for audit in audits:
        label = "player-list" if audit["alias"] == PLAYER_LIST_ALIAS else "nameplate"
        target_images = audit.pop("images")
        save_labeled_grid(
            output / f"{label}-bap-pipeline.png",
            [(stage, target_images[TARGET][stage]) for stage in ("direct", "source", "candidate")],
        )
        save_labeled_grid(
            output / f"{label}-bap-rasterizer-study.png",
            [
                (stage, target_images[TARGET][stage])
                for stage in (
                    "direct",
                    "shiftedUp1",
                    "plus1pxFit",
                    "oversampled2xBox",
                    "oversampled3xBox",
                    "oversampled2xLanczos",
                    "oversampled4x",
                )
            ],
        )
        comparison_columns = []
        for codepoint in (TARGET, *COMPARISONS):
            for stage in ("direct", "source"):
                comparison_columns.append((f"U+{codepoint:04X} {stage}", target_images[codepoint][stage]))
        save_labeled_grid(output / f"{label}-comparison-glyphs.png", comparison_columns)
        _source_path, source_font, source_pages = load_font_assets(
            parser_module, source_root, audit["alias"]
        )
        target = glyph_data(source_font, source_pages, TARGET)
        ttf_path = Path(audit["source_font"])
        alternatives = {
            "current": target["alpha"],
            "shiftedUp1": shifted_up_cell(target["alpha"]),
            "plus1pxFit": plus_one_size_cell(
                ttf_path,
                audit["actual_px_size"],
                TARGET,
                source_font.line_height,
                source_font.baseline,
                target["metric"][1],
                source_pages[target["page"]].kind,
            ),
            "oversampled2xBox": oversampled_cell(
                ttf_path,
                audit["actual_px_size"],
                TARGET,
                source_font.line_height,
                source_font.baseline,
                target["metric"][1],
                source_pages[target["page"]].kind,
                2,
                Image.Resampling.BOX,
            ),
        }
        save_labeled_grid(
            output / f"{label}-bap-phrase-study.png",
            [
                (
                    stage,
                    image_from_alpha(
                        compose_phrase(
                            source_font,
                            source_pages,
                            "브루노\u00A0밥티스타",
                            alpha,
                        ),
                        8,
                    ),
                )
                for stage, alpha in alternatives.items()
            ],
        )

    # The three requested pre-runtime views.  Direct contains both exact route
    # sizes because there is no single common size between the two renderers.
    direct_columns = []
    for audit in audits:
        label = f"{audit['weight']}{audit['actual_px_size']}"
        source_path, source_font, source_pages = load_font_assets(parser_module, source_root, audit["alias"])
        glyph = glyph_data(source_font, source_pages, TARGET)
        font = ImageFont.truetype(audit["source_font"], audit["actual_px_size"])
        direct, _metric, _bounds = direct_cell(
            font, TARGET, source_font.line_height, source_font.baseline, glyph["metric"][1], source_pages[glyph["page"]].kind
        )
        direct_columns.append((label, image_from_alpha(direct)))
    save_labeled_grid(output / "01-pretendard-direct-bap.png", direct_columns)

    for number, audit in enumerate(audits, start=2):
        label = "player-list" if audit["alias"] == PLAYER_LIST_ALIAS else "nameplate"
        _path, font, pages = load_font_assets(parser_module, source_root, audit["alias"])
        source = glyph_data(font, pages, TARGET)
        save_labeled_grid(
            output / f"0{number}-{label}-source-bap.png",
            [(f"{audit['alias']} source", image_from_alpha(source["alpha"]))],
        )

    all_rows = [row for audit in audits for row in audit["rows"]]
    direct_failures = [
        {"alias": audit["alias"], "codepoint": row["codepoint"], **row["direct_vs_source"]}
        for audit in audits
        for row in audit["rows"]
        if row["direct_vs_source"]["different_pixels"]
    ]
    append_failures = [
        {"alias": audit["alias"], "codepoint": row["codepoint"], **row["source_vs_candidate"]}
        for audit in audits
        for row in audit["rows"]
        if row["source_vs_candidate"]["different_pixels"]
    ]
    report = {
        "schema": "ams2-kr-068.1-ai-append-raster-pipeline-audit-v1",
        "target": {"codepoint": "U+BC25", "character": "밥"},
        "comparison_characters": [
            {"codepoint": f"U+{codepoint:04X}", "character": chr(codepoint)}
            for codepoint in COMPARISONS
        ],
        "route_evidence": {
            "player_list": {
                "bgui": "GUI/menu_mainmenu_1_6.bgui",
                "region": "Driver Network/list records adjacent to ordinals 5666-5739",
                "font": PLAYER_LIST_ALIAS,
            },
            "nameplate": {
                "bff": "Pakfiles/IGPHASEHUD.bff",
                "entry": "gui/hud_infoabovecar.bgui",
                "object": "ProfileName",
                "font": NAMEPLATE_ALIAS,
            },
        },
        "pillow": {
            "version": Image.__version__,
            "freetype_version": features.version_module("freetype2"),
        },
        "audited_new_codepoints": len(new_codepoints),
        "audited_route_glyphs": len(all_rows),
        "direct_vs_source_failures": direct_failures,
        "source_vs_candidate_failures": append_failures,
        "fonts": audits,
        "status": "PASS" if not direct_failures and not append_failures else "DIVERGENCE_FOUND",
    }
    (output / "ai-append-raster-pipeline-audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "new_codepoints": len(new_codepoints),
                "route_glyphs": len(all_rows),
                "direct_vs_source_failures": len(direct_failures),
                "source_vs_candidate_failures": len(append_failures),
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
