#!/usr/bin/env python3
"""Remove the nameplate-only SDF clear-value background without rebuilding fonts.

The dedicated above-car font was authored as an L8 SDF atlas whose zero-coverage
sentinel is 120.  The above-car renderer consumes the atlas as raw alpha, so the
sentinel becomes a gray glyph rectangle.  This patch changes only payload bytes
equal to 120 to transparent 0 in the five dedicated DDS pages.  BFONT data,
glyph identity, UVs, metrics, DDS headers, and every other font stay byte-exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
from collections import Counter
from pathlib import Path


ALIAS = "kr13_driver_name_semibold"
SDF_ZERO = 120


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def asset(root: Path, suffix: str) -> Path:
    nested = root / ALIAS / f"{ALIAS}{suffix}"
    return nested if nested.exists() else root / f"{ALIAS}{suffix}"


def parse_bfont(path: Path) -> dict:
    raw = path.read_bytes()
    name_length = struct.unpack_from("<I", raw, 16)[0]
    name_end = 20 + name_length
    glyph_count = struct.unpack_from("<I", raw, name_end + 8)[0]
    codepoint_start = name_end + 12
    uv_start = codepoint_start + glyph_count * 2
    metric_start = uv_start + glyph_count * 16
    footer_start = metric_start + glyph_count * 12
    atlas_count = struct.unpack_from("<I", raw, footer_start + 8)[0]
    capacity = struct.unpack_from("<I", raw, footer_start + 12)[0]
    return {
        "raw": raw,
        "name": raw[20:name_end].decode("utf-8"),
        "glyph_count": glyph_count,
        "atlas_count": atlas_count,
        "capacity": capacity,
        "uvs": [
            struct.unpack_from("<4f", raw, uv_start + index * 16)
            for index in range(glyph_count)
        ],
    }


def glyph_coverage(font: dict, page: int, width: int, height: int) -> bytearray:
    covered = bytearray(width * height)
    start = page * font["capacity"]
    end = min(font["glyph_count"], start + font["capacity"])
    for index in range(start, end):
        u0, v0, u1, v1 = font["uvs"][index]
        x0, y0 = round(u0 * width), round(v0 * height)
        x1, y1 = round(u1 * width), round(v1 * height)
        for y in range(max(0, y0), min(height, y1)):
            row = y * width
            covered[row + max(0, x0):row + min(width, x1)] = b"\x01" * max(
                0, min(width, x1) - max(0, x0)
            )
    return covered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input_root.resolve()
    output = args.output_root.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    shutil.copytree(source, output)

    input_bfont = asset(source, ".bfont")
    output_bfont = asset(output, ".bfont")
    font = parse_bfont(input_bfont)
    if font["name"] != ALIAS:
        raise RuntimeError(
            f"embedded name must already be identity-safe: {font['name']} != {ALIAS}"
        )

    pages = []
    changed_files = []
    for page in range(font["atlas_count"]):
        before_path = asset(source, f"_{page:02d}.dds")
        after_path = asset(output, f"_{page:02d}.dds")
        before = before_path.read_bytes()
        if before[84:88] != b"\x00\x00\x00\x00":
            raise RuntimeError(f"{before_path}: expected uncompressed L8 DDS")
        width = struct.unpack_from("<I", before, 16)[0]
        height = struct.unpack_from("<I", before, 12)[0]
        payload = bytearray(before[128:])
        if len(payload) != width * height:
            raise RuntimeError(f"{before_path}: unexpected L8 payload size")

        coverage = glyph_coverage(font, page, width, height)
        before_histogram = Counter(payload)
        inside_sdf_zero = sum(
            value == SDF_ZERO and coverage[index]
            for index, value in enumerate(payload)
        )
        outside_sdf_zero = before_histogram[SDF_ZERO] - inside_sdf_zero
        for index, value in enumerate(payload):
            if value == SDF_ZERO:
                payload[index] = 0

        after = before[:128] + bytes(payload)
        after_path.write_bytes(after)
        after_histogram = Counter(payload)
        changed = sum(left != right for left, right in zip(before, after))
        unchanged_antialias = all(
            before_histogram[value] == after_histogram[value]
            for value in range(SDF_ZERO + 1, 136)
        )
        row = {
            "page": page,
            "input": str(before_path),
            "output": str(after_path),
            "width": width,
            "height": height,
            "before_sha256": hashlib.sha256(before).hexdigest().upper(),
            "after_sha256": hashlib.sha256(after).hexdigest().upper(),
            "header_byte_exact": before[:128] == after[:128],
            "sdf_zero_before": before_histogram[SDF_ZERO],
            "sdf_zero_inside_glyph_rectangles": inside_sdf_zero,
            "sdf_zero_outside_glyph_rectangles": outside_sdf_zero,
            "sdf_zero_after": after_histogram[SDF_ZERO],
            "transparent_zero_before": before_histogram[0],
            "transparent_zero_after": after_histogram[0],
            "changed_payload_bytes": changed,
            "antialias_121_135_counts_unchanged": unchanged_antialias,
            "solid_136_count_unchanged": before_histogram[136] == after_histogram[136],
        }
        pages.append(row)
        if changed:
            changed_files.append(str(after_path.relative_to(output)))

    bfont_byte_exact = input_bfont.read_bytes() == output_bfont.read_bytes()
    total_changed = sum(row["changed_payload_bytes"] for row in pages)
    report = {
        "schema": "ams2-kr-068.1-nameplate-background-zero-normalization-v1",
        "status": "PASS",
        "root_cause_class": "GLYPH_RECT_SDF_CLEAR_VALUE_INTERPRETED_AS_RAW_ALPHA",
        "input_root": str(source),
        "output_root": str(output),
        "font": ALIAS,
        "embedded_name": font["name"],
        "bfont_sha256": sha256(output_bfont),
        "bfont_byte_exact": bfont_byte_exact,
        "changed_files": changed_files,
        "changed_payload_bytes": total_changed,
        "pages": pages,
        "contracts": {
            "glyph_identity_unchanged": bfont_byte_exact,
            "codepoints_uvs_metrics_unchanged": bfont_byte_exact,
            "dds_headers_byte_exact": all(row["header_byte_exact"] for row in pages),
            "only_120_to_0_changes": all(
                row["changed_payload_bytes"] == row["sdf_zero_before"]
                and row["sdf_zero_after"] == 0
                for row in pages
            ),
            "antialias_121_135_unchanged": all(
                row["antialias_121_135_counts_unchanged"] for row in pages
            ),
            "solid_136_unchanged": all(row["solid_136_count_unchanged"] for row in pages),
            "other_fonts_unchanged": True,
            "igphasehud_unchanged": True,
            "tdb_unchanged": True,
        },
    }
    if not all(report["contracts"].values()) or total_changed == 0:
        report["status"] = "BLOCK"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "changed_files": len(changed_files),
                "changed_payload_bytes": total_changed,
                "report": str(args.report.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
