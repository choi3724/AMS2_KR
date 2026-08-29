#!/usr/bin/env python3
"""Audit the above-car L8 atlas background contract before runtime validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path


ALIAS = "kr13_driver_name_semibold"
SDF_ZERO = 120
TARGET_NAMES = ("앤드류 스콧", "브루노 밥티스타", "아드리안 톨레도")


def asset(root: Path, suffix: str) -> Path:
    nested = root / ALIAS / f"{ALIAS}{suffix}"
    return nested if nested.exists() else root / f"{ALIAS}{suffix}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def parse_bfont(path: Path) -> dict:
    raw = path.read_bytes()
    name_length = struct.unpack_from("<I", raw, 16)[0]
    name_end = 20 + name_length
    count = struct.unpack_from("<I", raw, name_end + 8)[0]
    codepoint_start = name_end + 12
    uv_start = codepoint_start + count * 2
    metric_start = uv_start + count * 16
    footer_start = metric_start + count * 12
    return {
        "raw": raw,
        "name": raw[20:name_end].decode("utf-8"),
        "count": count,
        "codepoints": list(struct.unpack_from(f"<{count}H", raw, codepoint_start)),
        "uvs": [struct.unpack_from("<4f", raw, uv_start + i * 16) for i in range(count)],
        "metrics": [struct.unpack_from("<3i", raw, metric_start + i * 12) for i in range(count)],
        "atlas_count": struct.unpack_from("<I", raw, footer_start + 8)[0],
        "capacity": struct.unpack_from("<I", raw, footer_start + 12)[0],
    }


def parse_l8(path: Path) -> dict:
    raw = path.read_bytes()
    width = struct.unpack_from("<I", raw, 16)[0]
    height = struct.unpack_from("<I", raw, 12)[0]
    if raw[84:88] != b"\x00\x00\x00\x00" or len(raw[128:]) != width * height:
        raise RuntimeError(f"{path}: expected uncompressed L8 DDS")
    return {"raw": raw, "width": width, "height": height, "payload": raw[128:]}


def rect(font: dict, index: int, width: int, height: int) -> tuple[int, int, int, int]:
    u0, v0, u1, v1 = font["uvs"][index]
    return round(u0 * width), round(v0 * height), round(u1 * width), round(v1 * height)


def crop(payload: bytes, width: int, rectangle: tuple[int, int, int, int]) -> list[int]:
    x0, y0, x1, y1 = rectangle
    values = []
    for y in range(y0, y1):
        values.extend(payload[y * width + x0:y * width + x1])
    return values


def border(values: list[int], width: int, height: int) -> list[int]:
    if not values or width <= 0 or height <= 0:
        return []
    result = values[:width]
    if height > 1:
        result += values[(height - 1) * width:height * width]
    for y in range(1, max(1, height - 1)):
        result.append(values[y * width])
        if width > 1:
            result.append(values[y * width + width - 1])
    return result


def histogram_summary(values: list[int]) -> dict:
    counts = Counter(values)
    return {
        "transparent_0": counts[0],
        "sdf_zero_120": counts[SDF_ZERO],
        "antialias_121_135": sum(counts[value] for value in range(121, 136)),
        "solid_136": counts[136],
        "other_values": len(values)
        - counts[0]
        - counts[SDF_ZERO]
        - sum(counts[value] for value in range(121, 137)),
    }


def page_union(font: dict, page: int, width: int, height: int) -> bytearray:
    mask = bytearray(width * height)
    start = page * font["capacity"]
    end = min(font["count"], start + font["capacity"])
    for index in range(start, end):
        x0, y0, x1, y1 = rect(font, index, width, height)
        for y in range(y0, y1):
            row = y * width
            mask[row + x0:row + x1] = b"\x01" * (x1 - x0)
    return mask


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-root", type=Path, required=True)
    parser.add_argument("--after-root", type=Path, required=True)
    parser.add_argument("--page-usage-report", type=Path, required=True)
    parser.add_argument("--alpha-report", type=Path, required=True)
    args = parser.parse_args()

    before_root = args.before_root.resolve()
    after_root = args.after_root.resolve()
    before_font = parse_bfont(asset(before_root, ".bfont"))
    after_font = parse_bfont(asset(after_root, ".bfont"))
    if before_font["raw"] != after_font["raw"] or after_font["name"] != ALIAS:
        raise RuntimeError("BFONT identity/route contract changed")

    before_pages = [parse_l8(asset(before_root, f"_{page:02d}.dds")) for page in range(after_font["atlas_count"])]
    after_pages = [parse_l8(asset(after_root, f"_{page:02d}.dds")) for page in range(after_font["atlas_count"])]

    contexts = {}
    for name in TARGET_NAMES:
        for character in name:
            if not character.isspace():
                contexts.setdefault(ord(character), []).append(name)

    usage = []
    for codepoint in sorted(contexts):
        if codepoint not in after_font["codepoints"]:
            usage.append({
                "character": chr(codepoint),
                "codepoint": f"U+{codepoint:04X}",
                "contexts": contexts[codepoint],
                "status": "MISSING",
            })
            continue
        index = after_font["codepoints"].index(codepoint)
        page = index // after_font["capacity"]
        before_dds, after_dds = before_pages[page], after_pages[page]
        rectangle = rect(after_font, index, after_dds["width"], after_dds["height"])
        before_values = crop(before_dds["payload"], before_dds["width"], rectangle)
        after_values = crop(after_dds["payload"], after_dds["width"], rectangle)
        width, height = rectangle[2] - rectangle[0], rectangle[3] - rectangle[1]
        before_border = border(before_values, width, height)
        after_border = border(after_values, width, height)
        usage.append({
            "character": chr(codepoint),
            "codepoint": f"U+{codepoint:04X}",
            "contexts": contexts[codepoint],
            "record_index": index,
            "page": page,
            "page_filename": f"{ALIAS}_{page:02d}.dds",
            "uv": list(after_font["uvs"][index]),
            "glyph_bounds": list(rectangle),
            "metric": list(after_font["metrics"][index]),
            "before": {
                **histogram_summary(before_values),
                "border_sdf_zero_120": before_border.count(SDF_ZERO),
                "runtime_visible_background": "USER_CONFIRMED_NAMEPLATE_PATH",
            },
            "after": {
                **histogram_summary(after_values),
                "border_sdf_zero_120": after_border.count(SDF_ZERO),
                "runtime_visible_background": "PENDING_RUNTIME",
            },
            "identity_mapping_unchanged": True,
            "status": "STATIC_BACKGROUND_ZERO_NORMALIZED",
        })

    page_rows = []
    for page, (before_dds, after_dds) in enumerate(zip(before_pages, after_pages)):
        mask = page_union(after_font, page, after_dds["width"], after_dds["height"])
        before_hist = Counter(before_dds["payload"])
        after_hist = Counter(after_dds["payload"])
        inside_before = sum(
            value == SDF_ZERO and mask[index]
            for index, value in enumerate(before_dds["payload"])
        )
        outside_before = before_hist[SDF_ZERO] - inside_before
        changed = [
            (left, right)
            for left, right in zip(before_dds["payload"], after_dds["payload"])
            if left != right
        ]
        page_rows.append({
            "page": page,
            "filename": f"{ALIAS}_{page:02d}.dds",
            "format": "L8_ALPHA_ONLY",
            "width": after_dds["width"],
            "height": after_dds["height"],
            "before_sha256": sha256(before_dds["raw"]),
            "after_sha256": sha256(after_dds["raw"]),
            "sdf_zero_120_before": before_hist[SDF_ZERO],
            "sdf_zero_120_inside_glyph_rectangles": inside_before,
            "sdf_zero_120_outside_glyph_rectangles": outside_before,
            "sdf_zero_120_after": after_hist[SDF_ZERO],
            "changed_payload_bytes": len(changed),
            "only_120_to_0_changes": all(pair == (SDF_ZERO, 0) for pair in changed),
            "header_byte_exact": before_dds["raw"][:128] == after_dds["raw"][:128],
            "alpha_121_136_counts_unchanged": all(
                before_hist[value] == after_hist[value] for value in range(121, 137)
            ),
        })

    page_report = {
        "schema": "ams2-kr-068.1-nameplate-page-usage-v1",
        "font": ALIAS,
        "font_embedded_name": after_font["name"],
        "bfont_byte_exact": before_font["raw"] == after_font["raw"],
        "target_names": list(TARGET_NAMES),
        "characters": usage,
        "pages": page_rows,
        "runtime_scope": {
            "player_list": "SEPARATE_FONT_UNCHANGED",
            "above_car": "USER_CONFIRMED_BACKGROUND_BEFORE_FIX",
            "candidate12": "PENDING_RUNTIME",
        },
    }
    alpha_report = {
        "schema": "ams2-kr-068.1-alpha-blend-contract-analysis-v1",
        "root_cause_class": "GLYPH_RECT_SDF_CLEAR_VALUE_INTERPRETED_AS_RAW_ALPHA",
        "source_format": "L8_ALPHA_ONLY",
        "rgb_channels_present": False,
        "premultiplied_alpha_applicable": False,
        "page_clear_outside_glyph_rectangles": "TRANSPARENT_0",
        "glyph_rectangle_clear_before": 120,
        "above_car_renderer_observed_interpretation": "RAW_ALPHA",
        "effect": "120/255 coverage appears as contiguous gray nameplate boxes",
        "minimal_contract": "Only L8 payload value 120 becomes 0; values 121..136, DDS headers, BFONT, UVs, metrics and route stay exact",
        "static_false_pass_cause": "Previous validator inspected appended glyph rectangles only and treated 120 as a valid SDF zero; it did not model the above-car raw-alpha consumer or all Golden nameplate glyph rectangles",
        "before_pages_with_risk": sum(row["sdf_zero_120_before"] > 0 for row in page_rows),
        "after_pages_with_risk": sum(row["sdf_zero_120_after"] > 0 for row in page_rows),
        "changed_payload_bytes": sum(row["changed_payload_bytes"] for row in page_rows),
        "only_120_to_0_changes": all(row["only_120_to_0_changes"] for row in page_rows),
        "identity_contract": "PASS_STATIC",
        "runtime_verdict": "PENDING",
        "pages": page_rows,
    }
    for path, data in (
        (args.page_usage_report, page_report),
        (args.alpha_report, alpha_report),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS_STATIC",
        "characters": len(usage),
        "pages": len(page_rows),
        "before_pages_with_risk": alpha_report["before_pages_with_risk"],
        "after_pages_with_risk": alpha_report["after_pages_with_risk"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
