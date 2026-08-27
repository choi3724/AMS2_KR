#!/usr/bin/env python3
"""Build unified Pretendard UI BFONT/DDS resources for Closed Beta 0.6.

Existing kr*.bfont names remain stable.  All ordinary Latin, extended Latin,
Cyrillic, Greek, symbols and Hangul are rasterized from one Pretendard weight.
The two characters absent from Pretendard (⅔ and ⓒ) are composed from its own
glyphs.  Vehicle-display-only aliases are excluded by the route inventory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

if __name__ == "__main__" and "--append-only" in sys.argv:
    from ams2_golden_font_appender import main as append_only_main

    raise SystemExit(append_only_main([arg for arg in sys.argv[1:] if arg != "--append-only"]))

import numpy as np
from PIL import Image, ImageDraw, ImageFont


CAPACITY = 324
SENTINEL = 0x1234ABCD
ATLAS_GUTTER = 8
SDF_LOW = 120.0
SDF_HIGH = 136.0
DIMENSIONS = ((512, 512), (1024, 512), (1024, 1024), (2048, 512), (2048, 1024), (2048, 2048))
EXCLUDED_ALIASES = {"kr13_font_data_list", "kr13_font_heading_44"}
PIT_FONT_ALIAS = "kr13_font_hud_pit1"
PIT_HORIZONTAL_SCALE = 0.60
DRIVER_NAME_FONT_ALIAS = "kr13_driver_name_semibold"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def load_builder(path: Path):
    spec = importlib.util.spec_from_file_location("kr008_builder_for_unified_v06", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class BaseFont:
    scale_bits: int
    field_08: int
    field_0c: int
    name: str
    after_1: int
    after_2: int
    codepoints: tuple[int, ...]
    line_height: int
    baseline: int


@dataclass(frozen=True)
class Glyph:
    mask: Image.Image
    left: int
    top: int
    advance: int
    source: str


def parse_base_font(path: Path) -> BaseFont:
    data = path.read_bytes()
    _version, scale_bits, field_08, field_0c, name_len = struct.unpack_from("<IIIII", data, 0)
    name_end = 20 + name_len
    name = data[20:name_end].decode("utf-8")
    after_1, after_2, count = struct.unpack_from("<III", data, name_end)
    cp_start = name_end + 12
    uv_start = cp_start + count * 2
    metric_start = uv_start + count * 16
    footer_start = metric_start + count * 12
    codepoints = tuple(struct.unpack_from(f"<{count}H", data, cp_start))
    line_height, baseline = struct.unpack_from("<II", data, footer_start)
    return BaseFont(scale_bits, field_08, field_0c, name, after_1, after_2, codepoints, line_height, baseline)


def parse_builder_metrics(path: Path) -> tuple[tuple[int, int, int], ...]:
    data = path.read_bytes()
    name_len = struct.unpack_from("<I", data, 16)[0]
    name_end = 20 + name_len
    count = struct.unpack_from("<I", data, name_end + 8)[0]
    metric_start = name_end + 12 + count * 2 + count * 16
    return tuple(
        struct.unpack_from("<3i", data, metric_start + index * 12)
        for index in range(count)
    )


def parse_cmap(path: Path) -> set[int]:
    data = path.read_bytes()
    count = struct.unpack_from(">H", data, 4)[0]
    cmap_offset = next(
        offset for index in range(count)
        for tag, _check, offset, _length in [struct.unpack_from(">4sIII", data, 12 + index * 16)]
        if tag == b"cmap"
    )
    _version, sub_count = struct.unpack_from(">HH", data, cmap_offset)
    sub_offsets = {
        cmap_offset + relative
        for index in range(sub_count)
        for platform, encoding, relative in [struct.unpack_from(">HHI", data, cmap_offset + 4 + index * 8)]
        if platform == 0 or (platform == 3 and encoding in (1, 10))
    }
    mapped: set[int] = set()
    for sub in sub_offsets:
        fmt = struct.unpack_from(">H", data, sub)[0]
        if fmt == 12:
            groups = struct.unpack_from(">I", data, sub + 12)[0]
            for index in range(groups):
                start, end, glyph = struct.unpack_from(">III", data, sub + 16 + index * 12)
                if glyph:
                    mapped.update(range(start, min(end, 0xFFFF) + 1))
        elif fmt == 4:
            seg_count = struct.unpack_from(">H", data, sub + 6)[0] // 2
            end_pos = sub + 14
            start_pos = end_pos + seg_count * 2 + 2
            delta_pos = start_pos + seg_count * 2
            range_pos = delta_pos + seg_count * 2
            for index in range(seg_count):
                end = struct.unpack_from(">H", data, end_pos + index * 2)[0]
                start = struct.unpack_from(">H", data, start_pos + index * 2)[0]
                delta = struct.unpack_from(">h", data, delta_pos + index * 2)[0]
                range_address = range_pos + index * 2
                range_offset = struct.unpack_from(">H", data, range_address)[0]
                for cp in range(start, end + 1):
                    if cp == 0xFFFF:
                        continue
                    if range_offset == 0:
                        glyph = (cp + delta) & 0xFFFF
                    else:
                        glyph_address = range_address + range_offset + (cp - start) * 2
                        glyph = struct.unpack_from(">H", data, glyph_address)[0]
                        if glyph:
                            glyph = (glyph + delta) & 0xFFFF
                    if glyph:
                        mapped.add(cp)
    return mapped


def parse_corpus(path: Path) -> tuple[int, ...]:
    return tuple(int(line[2:6], 16) for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("U+"))


LATIN_METRIC_SAMPLE = tuple([
    *range(ord("0"), ord("9") + 1),
    *range(ord("A"), ord("Z") + 1),
    *range(ord("a"), ord("z") + 1),
])


def metric_profile(metrics: dict[int, tuple[int, int, int]]) -> dict[str, float]:
    rows = [metrics[cp] for cp in LATIN_METRIC_SAMPLE if cp in metrics and metrics[cp][1] > 0]
    if not rows:
        raise RuntimeError("no Latin metric sample")
    widths = np.asarray([row[1] for row in rows], dtype=np.float64)
    advances = np.asarray([row[2] for row in rows], dtype=np.float64)
    hangul_advances = np.asarray(
        [row[2] for cp, row in metrics.items() if 0xAC00 <= cp <= 0xD7A3 and row[1] > 0],
        dtype=np.float64,
    )
    return {
        "median_width": float(np.median(widths)),
        "median_advance": float(np.median(advances)),
        "p90_advance": float(np.percentile(advances, 90)),
        "maximum_advance": float(np.max(advances)),
        "hangul_median_advance": float(np.median(hangul_advances)) if len(hangul_advances) else 0.0,
    }


def metrics_fit_legacy(candidate: dict[str, float], legacy: dict[str, float]) -> bool:
    return (
        candidate["median_advance"] <= legacy["median_advance"]
        and candidate["p90_advance"] <= legacy["p90_advance"] * 1.08
        and candidate["maximum_advance"] <= legacy["maximum_advance"] * 1.08
    )


def weight_and_size(stem: str) -> tuple[str, int, str]:
    if stem == DRIVER_NAME_FONT_ALIAS:
        return "SemiBold", 20, "dedicated driving HUD opponent nameplate"
    if "page_title" in stem:
        return "ExtraBold", 46, "large page title"
    explicit = re.search(r"_(?:standard|heading)_(\d+)$", stem)
    if explicit:
        return ("Bold" if "heading" in stem else "Medium"), int(explicit.group(1)), "explicit nominal size"
    if "heading" in stem:
        return "Bold", 24, "section title"
    if "hud_bold" in stem:
        return "Bold", 20, "important HUD and pit label legibility"
    if "hud_pos" in stem:
        return "SemiBold", 36, "HUD position"
    if "hud_tach_num" in stem:
        return "SemiBold", 24, "HUD numeric"
    if "hud_" in stem:
        return "SemiBold", 20, "general HUD"
    if "session_time" in stem:
        return "SemiBold", 64, "session timer"
    if "aries_large" in stem:
        return "SemiBold", 24, "important UI"
    if "aries_small" in stem or "tab_title" in stem:
        return "SemiBold", 17, "compact important UI"
    if "body_large" in stem:
        return "Medium", 22, "large body"
    if "body_regular" in stem:
        return "Medium", 24, "body"
    if "body_footnote" in stem or "data_list" in stem:
        return "Medium", 17, "body or setting value"
    if "mono_16" in stem:
        return "Medium", 16, "general technical text"
    if "styletest" in stem:
        return "Medium", 18, "general UI"
    return "Medium", 17, "general UI"


def direct_glyph(font: ImageFont.FreeTypeFont, cp: int) -> Glyph:
    char = chr(cp)
    left, top, right, bottom = font.getbbox(char, anchor="ls")
    mask = Image.new("L", (max(0, right - left), max(0, bottom - top)), 0)
    if mask.width and mask.height:
        ImageDraw.Draw(mask).text((-left, -top), char, font=font, fill=255, anchor="ls")
    return Glyph(mask, left, top, int(math.floor(font.getlength(char) + 0.5)), "PRETENDARD_DIRECT")


def condense_glyph(glyph: Glyph, scale: float) -> Glyph:
    """Keep pit-label height while fitting two Hangul glyphs into 21 px."""
    if glyph.mask.width == 0:
        return glyph
    width = max(1, int(math.floor(glyph.mask.width * scale + 0.5)))
    mask = glyph.mask.resize((width, glyph.mask.height), Image.Resampling.LANCZOS)
    left = int(math.floor(glyph.left * scale + 0.5))
    advance = max(1, int(math.floor(glyph.advance * scale + 0.5)))
    return Glyph(mask, left, glyph.top, advance, f"{glyph.source}_PIT_CONDENSED")


def composed_glyph(font: ImageFont.FreeTypeFont, cp: int) -> Glyph:
    if cp not in (0x2154, 0x24D2):
        raise RuntimeError(f"Pretendard lacks unsupported U+{cp:04X}")
    ascent, _descent = font.getmetrics()
    canvas = Image.new("L", (font.size * 4, (ascent + font.size) * 2), 0)
    draw = ImageDraw.Draw(canvas)
    origin = (font.size, font.size + ascent)
    if cp == 0x2154:
        small = ImageFont.truetype(font.path, max(6, round(font.size * 0.72)))
        text = "2/3"
        draw.text(origin, text, font=small, fill=255, anchor="ls")
        advance = int(math.floor(small.getlength(text) + 0.5))
    else:
        small = ImageFont.truetype(font.path, max(6, round(font.size * 0.72)))
        letter_width = int(math.ceil(small.getlength("c")))
        diameter = max(letter_width + 4, round(font.size * 0.8))
        draw.ellipse((origin[0], origin[1] - diameter, origin[0] + diameter, origin[1]), outline=255, width=max(1, font.size // 14))
        draw.text((origin[0] + (diameter - letter_width) // 2, origin[1] - max(1, font.size // 9)), "c", font=small, fill=255, anchor="ls")
        advance = diameter
    box = canvas.getbbox()
    if box is None:
        raise RuntimeError(f"empty composed U+{cp:04X}")
    return Glyph(canvas.crop(box), box[0] - origin[0], box[1] - origin[1], advance, "PRETENDARD_COMPOSED")


def layout(widths: list[int], line_height: int, width: int, height: int) -> list[tuple[int, int, int, int]] | None:
    # AMS2 samples the atlas with filtering enabled.  Keep one complete DXT3
    # block around every row so neighbouring glyph rows cannot bleed into the
    # rendered text.  The first row also needs a guard against texture-edge
    # sampling.
    x = y = ATLAS_GUTTER
    result = []
    for glyph_width in widths:
        x = (x + 3) // 4 * 4
        if glyph_width and x + glyph_width > width:
            y = (y + line_height + 3) // 4 * 4 + ATLAS_GUTTER
            x = ATLAS_GUTTER
        if y + line_height + ATLAS_GUTTER > height:
            return None
        result.append((x, y, x + glyph_width, y + line_height))
        if glyph_width:
            x = (x + glyph_width + 3) // 4 * 4 + ATLAS_GUTTER
    return result


def select_dimensions(widths: list[int], line_height: int) -> tuple[int, int]:
    chunks = [widths[index:index + CAPACITY] for index in range(0, len(widths), CAPACITY)]
    viable = [dims for dims in DIMENSIONS if all(layout(chunk, line_height, *dims) is not None for chunk in chunks)]
    if not viable:
        raise RuntimeError(f"glyph layout does not fit: line_height={line_height}")
    return min(viable, key=lambda dims: (dims[0] * dims[1], max(dims), dims[0]))


def dxt3_payload(raw: bytes, width: int, height: int) -> bytes:
    alpha = np.frombuffer(raw, dtype=np.uint8).reshape(height, width)
    blocks = alpha.reshape(height // 4, 4, width // 4, 4).transpose(0, 2, 1, 3)
    nibbles = ((blocks.astype(np.uint16) * 15 + 127) // 255).astype(np.uint16)
    packed = (nibbles[:, :, :, 0] | (nibbles[:, :, :, 1] << 4) | (nibbles[:, :, :, 2] << 8) | (nibbles[:, :, :, 3] << 12)).astype("<u2")
    output = np.zeros((height // 4, width // 4, 16), dtype=np.uint8)
    packed_bytes = np.ascontiguousarray(packed).view(np.uint8)
    output[:, :, :8] = packed_bytes.reshape(height // 4, width // 4, 8)
    output[:, :, 8:10] = 0xFF
    zero = (blocks.reshape(height // 4, width // 4, 16) == 0).astype(np.uint32)
    shifts = (np.arange(16, dtype=np.uint32) * 2).reshape(1, 1, 16)
    indices = np.bitwise_or.reduce(zero << shifts, axis=2).astype("<u4")
    index_bytes = np.ascontiguousarray(indices).view(np.uint8)
    output[:, :, 12:16] = index_bytes.reshape(height // 4, width // 4, 4)
    return output.tobytes()


def make_dds(template, width: int, height: int, payload: bytes) -> bytes:
    """Reuse the proven classic DDS header while updating dimensions/stride."""
    if width == template.width and height == template.height and len(payload) == len(template.payload):
        return template.header + payload
    header = bytearray(template.header)
    stride = width if template.kind == "L8" else len(payload)
    struct.pack_into("<III", header, 12, height, width, stride)
    struct.pack_into("<I", header, 28, 1)
    return bytes(header) + payload


def coverage_to_l8_sdf(coverage: Image.Image, rect_mask: Image.Image) -> bytes:
    """Encode native FreeType coverage into AMS2's proven 120..136 L8 band.

    AMS2's L8 text shader converts this band back to 0..255 coverage.  Writing
    raw 0..255 coverage into an L8 atlas makes that shader threshold it twice,
    which caused the jagged/outlined 0.6 result.  This inverse transfer keeps
    every TrueType antialiasing level while preserving the shader contract.
    """
    cov = np.asarray(coverage, dtype=np.uint8)
    field = np.rint(SDF_LOW + cov.astype(np.float32) * (SDF_HIGH - SDF_LOW) / 255.0).astype(np.uint8)
    field[np.asarray(rect_mask, dtype=np.uint8) == 0] = 0
    return field.tobytes()


def render_pages(module, template, codepoints: tuple[int, ...], glyphs: list[Glyph], line_height: int, baseline: int, width: int, height: int) -> tuple[list[bytes], list[tuple[float, float, float, float]]]:
    pages, uvs = [], []
    for start in range(0, len(codepoints), CAPACITY):
        chunk = glyphs[start:start + CAPACITY]
        rects = layout([glyph.mask.width for glyph in chunk], line_height, width, height)
        if rects is None:
            raise RuntimeError("layout changed after dimension selection")
        image = Image.new("L", (width, height), 0)
        rect_mask = Image.new("L", (width, height), 0)
        rect_draw = ImageDraw.Draw(rect_mask)
        for cp, glyph, rect in zip(codepoints[start:start + CAPACITY], chunk, rects):
            x0, y0, x1, y1 = rect
            uvs.append((x0 / width, y0 / height, x1 / width, y1 / height))
            if glyph.mask.width:
                rect_draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
                paste_y = y0 + baseline + glyph.top
                if paste_y < y0 or paste_y + glyph.mask.height > y1:
                    raise RuntimeError(f"U+{cp:04X} vertical overflow")
                # glyph.mask already is the FreeType coverage field.  Passing
                # it again as a PIL paste mask would square every alpha value
                # and make small text unnaturally thin and fragmented.
                image.paste(glyph.mask, (x0, paste_y))
        raw = image.tobytes()
        payload = coverage_to_l8_sdf(image, rect_mask) if template.kind == "L8" else dxt3_payload(raw, width, height)
        pages.append(make_dds(template, width, height, payload))
    return pages, uvs


def build_bfont(base: BaseFont, codepoints: tuple[int, ...], uvs: list[tuple[float, float, float, float]], glyphs: list[Glyph], line_height: int, baseline: int, atlas_count: int) -> bytes:
    name = base.name.encode("ascii")
    header = struct.pack("<IIIII", 10, base.scale_bits, base.field_08, base.field_0c, len(name)) + name + struct.pack("<III", base.after_1, base.after_2, len(codepoints))
    cp_data = struct.pack(f"<{len(codepoints)}H", *codepoints)
    uv_data = b"".join(struct.pack("<4f", *uv) for uv in uvs)
    metrics = b"".join(struct.pack("<3i", glyph.left, glyph.mask.width, glyph.advance) for glyph in glyphs)
    footer = struct.pack("<IIIIIII", line_height, baseline, atlas_count, CAPACITY, 0, 0, SENTINEL)
    return header + cp_data + uv_data + metrics + footer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-gui", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--font-root", type=Path, required=True)
    parser.add_argument("--hangul-corpus", type=Path, required=True)
    parser.add_argument("--builder", type=Path, required=True)
    parser.add_argument("--pit-template-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    payload_gui = args.payload_gui.resolve()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    module = load_builder(args.builder.resolve())
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise SystemExit(f"refusing existing output root: {output_root}")
    output_root.mkdir(parents=True)

    reference = parse_base_font(payload_gui / "kr08_font_standard_22.bfont")
    # AMS2 handles U+0020 outside the BFONT lookup table.  The shipped and
    # proven Korean BFONTs intentionally begin at U+0021; inserting a space at
    # index zero makes the runtime draw the following exclamation glyph for
    # every space.
    requested = tuple(sorted({*reference.codepoints, *parse_corpus(args.hangul_corpus.resolve())} - {0x20}))
    eligible = sorted({Path(row["font"]).stem for row in inventory["fonts"] if row["font"].startswith("gui\\kr") and row["classification"] != "VEHICLE_DISPLAY" and Path(row["font"]).stem not in EXCLUDED_ALIASES})
    build_specs = [(stem, stem, False) for stem in eligible]
    build_specs.append((PIT_FONT_ALIAS, "kr13_font_hud_main", True))
    build_specs.append((DRIVER_NAME_FONT_ALIAS, "kr13_phoenix_body_regular", False))

    sources = {}
    cmaps = {}
    for weight in ("Medium", "SemiBold", "Bold", "ExtraBold"):
        candidates = [
            args.font_root.resolve() / f"Pretendard-{weight}.ttf",
            args.font_root.resolve() / f"Pretendard-{weight}.otf",
        ]
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            raise RuntimeError(f"missing Pretendard {weight}: {candidates}")
        data = path.read_bytes()
        sources[weight] = {"path": str(path), "bytes": len(data), "sha256": sha256(data)}
        cmaps[weight] = parse_cmap(path)

    rows = []
    for stem, base_stem, dedicated_pit in build_specs:
        base = parse_base_font(payload_gui / f"{base_stem}.bfont")
        base_metrics = dict(zip(base.codepoints, parse_builder_metrics(payload_gui / f"{base_stem}.bfont")))
        legacy_profile = metric_profile(base_metrics)
        weight, requested_size, reason = weight_and_size(stem)
        if dedicated_pit:
            requested_size = 20
            reason = "dedicated HUD Beta pit label; intentionally larger than shared HUD text"
        source_path = Path(sources[weight]["path"])
        for size in range(requested_size, 7, -1):
            font = ImageFont.truetype(str(source_path), size)
            ascent, descent = font.getmetrics()
            glyphs = [
                Glyph(Image.new("L", (0, 0), 0), base_metrics[cp][0], 0, base_metrics[cp][2], "BASE_EMPTY_SENTINEL")
                if cp in base_metrics and base_metrics[cp][1] == 0
                else direct_glyph(font, cp)
                if cp in cmaps[weight]
                else composed_glyph(font, cp)
                for cp in requested
            ]
            if dedicated_pit:
                glyphs = [condense_glyph(glyph, PIT_HORIZONTAL_SCALE) for glyph in glyphs]
            top = min([-ascent, *(glyph.top for glyph in glyphs if glyph.mask.height)])
            bottom = max([descent, *(glyph.top + glyph.mask.height for glyph in glyphs if glyph.mask.height)])
            actual_line_height = bottom - top
            candidate_profile = metric_profile({cp: (glyph.left, glyph.mask.width, glyph.advance) for cp, glyph in zip(requested, glyphs)})
            if actual_line_height <= base.line_height and (dedicated_pit or metrics_fit_legacy(candidate_profile, legacy_profile)):
                break
        else:
            raise RuntimeError(f"cannot fit Pretendard glyph bounds into {stem} line box")
        # BGUI geometry was authored against the existing BFONT line box.
        # Preserve that box while keeping Pretendard's real glyph bearings,
        # widths and advances.  Clamp the legacy baseline only when the new
        # glyph bounds would otherwise cross the line box.
        line_height = base.line_height
        minimum_baseline = -top
        maximum_baseline = line_height - bottom
        if minimum_baseline > maximum_baseline:
            raise RuntimeError(f"Pretendard glyph bounds exceed {stem} line box")
        baseline = min(max(base.baseline, minimum_baseline), maximum_baseline)
        template_path = (
            args.pit_template_root.resolve() / f"{PIT_FONT_ALIAS}_00.dds"
            if dedicated_pit and args.pit_template_root
            else payload_gui / f"{base_stem}_00.dds"
        )
        template = module.parse_dds(template_path.read_bytes(), str(template_path))
        width, height = (
            (template.width, template.height)
            if dedicated_pit
            else select_dimensions([glyph.mask.width for glyph in glyphs], line_height)
        )
        pages, uvs = render_pages(module, template, requested, glyphs, line_height, baseline, width, height)
        bfont = build_bfont(base, requested, uvs, glyphs, line_height, baseline, len(pages))
        parsed = module.parse_bfont(bfont, stem)
        if parsed.codepoints != requested or parsed.metrics != tuple((g.left, g.mask.width, g.advance) for g in glyphs):
            raise RuntimeError(f"BFONT roundtrip failed: {stem}")
        target = output_root / stem
        target.mkdir()
        (target / f"{stem}.bfont").write_bytes(bfont)
        for index, page in enumerate(pages):
            (target / f"{stem}_{index:02d}.dds").write_bytes(page)
        manifest = {
            "schema": "ams2-kr-beta-0.6-pretendard-unified-font-v1",
            "status": "PASS",
            "alias": stem,
            "base_alias": base_stem,
            "dedicated_pit_label": dedicated_pit,
            "weight": weight,
            "pixel_size": size,
            "requested_pixel_size": requested_size,
            "weight_reason": reason,
            "source_font": sources[weight],
            "glyph_count": len(requested),
            "glyph_sources": dict(sorted(Counter(glyph.source for glyph in glyphs).items())),
            "line_height": line_height,
            "baseline": baseline,
            "actual_glyph_bounds": {"top": top, "bottom": bottom, "height": actual_line_height},
            "old_line_height": base.line_height,
            "old_baseline": base.baseline,
            "metrics_source": "Pillow FreeType from Pretendard static TrueType/OpenType source",
            "source_outline_format": source_path.suffix.upper().lstrip("."),
            "legacy_metric_profile": legacy_profile,
            "generated_metric_profile": candidate_profile,
            "layout_calibration": "largest size within legacy Latin advance envelope" if not dedicated_pit else "intentional pit-only size override",
            "horizontal_scale": PIT_HORIZONTAL_SCALE if dedicated_pit else 1.0,
            "metric_contract": {"field_0":"left_bearing", "field_1":"raster_width", "field_2":"rounded_advance"},
            "space_policy": "U+0020 omitted; AMS2 runtime handles spaces outside BFONT",
            "kerning_records": 0,
            "atlas": {"count":len(pages), "capacity":CAPACITY, "dimensions":[width,height], "pixel_format":template.kind, "l8_strategy":"FREETYPE_COVERAGE_INVERSE_ENCODED_TO_SDF_120_136" if template.kind == "L8" else "NATIVE_FREETYPE_COVERAGE_DXT3"},
            "bfont": {"bytes":len(bfont), "sha256":sha256(bfont)},
            "dds": [{"file":f"{stem}_{index:02d}.dds", "bytes":len(page), "sha256":sha256(page)} for index,page in enumerate(pages)],
            "checks": {"strict_parse":True, "sorted_unique":len(requested)==len(set(requested)), "missing_glyphs":False, "single_family_latin_hangul":True},
        }
        (target / f"{stem}.font-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rows.append(manifest)
        print(f"built {stem}: {weight} {size}px, {len(pages)}x{width}x{height} {template.kind}")

    summary = {
        "schema": "ams2-kr-beta-0.6-pretendard-unified-family-v1",
        "status": "PASS",
        "font_count": len(rows),
        "glyph_count_per_font": len(requested),
        "source_fonts": sources,
        "excluded_aliases": sorted(EXCLUDED_ALIASES),
        "fonts": [{key:row[key] for key in ("alias","weight","pixel_size","line_height","baseline","old_line_height","old_baseline","atlas","bfont")} for row in rows],
    }
    (output_root / "build-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status":"PASS", "font_count":len(rows), "output":str(output_root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
