#!/usr/bin/env python3
"""Validate append-only AMS2 font atlases against Golden and v0.6.8.

The v0.6.8 L8 source uses 120 as its zero-coverage SDF sentinel.  AMS2 draws
that raw value as a gray rectangle.  Release candidates must normalize only
those appended L8 pixels to 0 and must keep DXT3 data byte-exact to v0.6.8.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


SDF_ZERO = 120
EXCLUDED = {"kr13_font_data_list", "kr13_font_heading_44"}
DRIVER_NAME = "kr13_driver_name_semibold"
BLOCKING = {0xCF67, 0xBC25, 0xD1A8}


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def font_path(root: Path, alias: str, suffix: str) -> Path:
    nested = root / alias / f"{alias}{suffix}"
    return nested if nested.exists() else root / f"{alias}{suffix}"


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
        "uvs": [struct.unpack_from("<4f", raw, uv_start + index * 16) for index in range(count)],
        "metrics": [struct.unpack_from("<3i", raw, metric_start + index * 12) for index in range(count)],
        "codepoint_bytes": raw[codepoint_start:uv_start],
        "uv_bytes": raw[uv_start:metric_start],
        "metric_bytes": raw[metric_start:footer_start],
        "footer": raw[footer_start:],
        "atlas_count": struct.unpack_from("<I", raw, footer_start + 8)[0],
        "capacity": struct.unpack_from("<I", raw, footer_start + 12)[0],
    }


def parse_dds(path: Path) -> dict:
    raw = path.read_bytes()
    fourcc = raw[84:88]
    return {
        "raw": raw,
        "header": raw[:128],
        "payload": raw[128:],
        "width": struct.unpack_from("<I", raw, 16)[0],
        "height": struct.unpack_from("<I", raw, 12)[0],
        "kind": "DXT3" if fourcc == b"DXT3" else "L8",
    }


def rectangle(font: dict, index: int, dds: dict) -> tuple[int, int, int, int]:
    u = font["uvs"][index]
    return (round(u[0] * dds["width"]), round(u[1] * dds["height"]), round(u[2] * dds["width"]), round(u[3] * dds["height"]))


def blocks(rect: tuple[int, int, int, int], width: int) -> set[int]:
    x0, y0, x1, y1 = rect
    if x0 == x1:
        return set()
    stride = width // 4
    return {y * stride + x for y in range(y0 // 4, (y1 + 3) // 4) for x in range(x0 // 4, (x1 + 3) // 4)}


def dxt_alpha(dds: dict, rect: tuple[int, int, int, int]) -> list[int]:
    x0, y0, x1, y1 = rect
    stride = dds["width"] // 4
    values = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            block = (y // 4) * stride + x // 4
            word = struct.unpack_from("<H", dds["payload"], block * 16 + (y % 4) * 2)[0]
            values.append(((word >> ((x % 4) * 4)) & 15) * 17)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-root", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--allowed-raster-manifest",
        type=Path,
        help="optional exact U+BC25 raster micro-patch manifest",
    )
    parser.add_argument(
        "--nameplate-background-manifest",
        type=Path,
        help="optional exact dedicated-nameplate 120-to-0 normalization manifest",
    )
    args = parser.parse_args()

    allowed_rasters = {}
    if args.allowed_raster_manifest:
        allowed_data = json.loads(args.allowed_raster_manifest.read_text(encoding="utf-8"))
        if allowed_data.get("status") != "PASS" or allowed_data.get("target", {}).get("codepoint") != "U+BC25":
            raise RuntimeError("allowed raster manifest contract mismatch")
        allowed_rasters = {
            row["alias"]: {"page": int(row["page"]), "rect": tuple(row["rect"])}
            for row in allowed_data["routes"]
        }

    nameplate_background_pages = set()
    if args.nameplate_background_manifest:
        background_data = json.loads(
            args.nameplate_background_manifest.read_text(encoding="utf-8")
        )
        if (
            background_data.get("status") != "PASS"
            or background_data.get("font") != DRIVER_NAME
            or not background_data.get("contracts", {}).get("only_120_to_0_changes")
        ):
            raise RuntimeError("nameplate background manifest contract mismatch")
        nameplate_background_pages = {
            int(row["page"])
            for row in background_data["pages"]
            if row["changed_payload_bytes"]
        }

    aliases = sorted(path.stem for path in args.golden_root.glob("*.bfont"))
    rows = []
    totals = {
        "fonts": len(aliases), "appended_fonts": 0, "appended_records": 0,
        "raw_l8_sdf_floor_pixels": 0, "l8_normalized_pixels": 0,
        "approved_l8_raster_changes": 0, "unexpected_l8_changes": 0,
        "dxt_baseline_byte_changes": 0,
        "golden_owned_pixel_changes": 0, "dxt_golden_block_collisions": 0,
        "golden_index_changes": 0, "golden_metric_changes": 0, "golden_uv_changes": 0,
        "embedded_name_mismatches": 0,
    }
    blocking_rows = []

    for alias in aliases:
        golden = parse_bfont(font_path(args.golden_root, alias, ".bfont"))
        baseline = parse_bfont(font_path(args.baseline_root, alias, ".bfont"))
        candidate = parse_bfont(font_path(args.candidate_root, alias, ".bfont"))
        totals["embedded_name_mismatches"] += candidate["name"] != alias
        if alias != DRIVER_NAME and candidate["raw"] != baseline["raw"]:
            raise RuntimeError(f"{alias}: BFONT differs from v0.6.8 baseline")
        prefix = golden["count"]
        totals["golden_index_changes"] += sum(left != right for left, right in zip(golden["codepoints"], candidate["codepoints"][:prefix]))
        totals["golden_metric_changes"] += sum(left != right for left, right in zip(golden["metrics"], candidate["metrics"][:prefix]))
        totals["golden_uv_changes"] += sum(left != right for left, right in zip(golden["uvs"], candidate["uvs"][:prefix]))

        appended = candidate["count"] - prefix
        expected = 0 if alias in EXCLUDED else 68 if alias == DRIVER_NAME else 69
        if appended != expected:
            raise RuntimeError(f"{alias}: appended {appended}, expected {expected}")
        totals["appended_fonts"] += appended > 0
        totals["appended_records"] += appended
        glyph_rows = []

        for page in range(candidate["atlas_count"]):
            golden_dds = parse_dds(font_path(args.golden_root, alias, f"_{page:02d}.dds"))
            baseline_dds = parse_dds(font_path(args.baseline_root, alias, f"_{page:02d}.dds"))
            candidate_dds = parse_dds(font_path(args.candidate_root, alias, f"_{page:02d}.dds"))
            page_indices = [index for index in range(prefix, candidate["count"]) if index // candidate["capacity"] == page]
            appended_rects = [(index, rectangle(candidate, index, candidate_dds)) for index in page_indices]

            if candidate_dds["kind"] == "DXT3":
                if candidate_dds["raw"] != baseline_dds["raw"]:
                    totals["dxt_baseline_byte_changes"] += sum(left != right for left, right in zip(candidate_dds["raw"], baseline_dds["raw"]))
                appended_blocks = set().union(*(blocks(rect, candidate_dds["width"]) for _, rect in appended_rects)) if appended_rects else set()
                golden_blocks = set()
                for index in range(prefix):
                    if index // golden["capacity"] == page:
                        golden_blocks |= blocks(rectangle(golden, index, golden_dds), golden_dds["width"])
                totals["dxt_golden_block_collisions"] += len(appended_blocks & golden_blocks)
                for block in range(len(candidate_dds["payload"]) // 16):
                    if block in appended_blocks:
                        continue
                    a = candidate_dds["payload"][block * 16:(block + 1) * 16]
                    b = golden_dds["payload"][block * 16:(block + 1) * 16]
                    totals["golden_owned_pixel_changes"] += sum(left != right for left, right in zip(a, b))
            else:
                appended_pixels = set()
                for _, (x0, y0, x1, y1) in appended_rects:
                    appended_pixels.update(y * candidate_dds["width"] + x for y in range(y0, y1) for x in range(x0, x1))
                allowed_pixels = set()
                allowed = allowed_rasters.get(alias)
                if allowed and allowed["page"] == page:
                    ax0, ay0, ax1, ay1 = allowed["rect"]
                    allowed_pixels.update(
                        y * candidate_dds["width"] + x
                        for y in range(ay0, ay1)
                        for x in range(ax0, ax1)
                    )
                for offset, (gold, base, value) in enumerate(zip(golden_dds["payload"], baseline_dds["payload"], candidate_dds["payload"])):
                    if offset not in appended_pixels:
                        if (
                            alias == DRIVER_NAME
                            and page in nameplate_background_pages
                            and base == SDF_ZERO
                            and value == 0
                        ):
                            totals["l8_normalized_pixels"] += 1
                        else:
                            totals["golden_owned_pixel_changes"] += value != gold
                    elif value != base:
                        if base == SDF_ZERO and value == 0:
                            totals["l8_normalized_pixels"] += 1
                        elif offset in allowed_pixels:
                            totals["approved_l8_raster_changes"] += 1
                        elif alias != DRIVER_NAME or allowed_rasters:
                            totals["unexpected_l8_changes"] += 1

            for index, rect in appended_rects:
                cp = candidate["codepoints"][index]
                if cp == 0x00A0:
                    continue
                if candidate_dds["kind"] == "L8":
                    x0, y0, x1, y1 = rect
                    values = []
                    for y in range(y0, y1):
                        values.extend(candidate_dds["payload"][y * candidate_dds["width"] + x0:y * candidate_dds["width"] + x1])
                    floor = values.count(SDF_ZERO)
                    zeros = values.count(0)
                    active = sum(value > SDF_ZERO for value in values)
                    totals["raw_l8_sdf_floor_pixels"] += floor
                else:
                    values = dxt_alpha(candidate_dds, rect)
                    floor = 0
                    zeros = values.count(0)
                    active = len(values) - zeros
                row = {"character": chr(cp), "codepoint": f"U+{cp:04X}", "font": alias, "index": index, "page": page, "pixel_format": candidate_dds["kind"], "rectangle": rect, "zero_pixels": zeros, "active_pixels": active, "raw_l8_sdf_floor_pixels": floor, "status": "PASS" if floor == 0 and zeros > 0 and active > 0 else "BLOCK"}
                glyph_rows.append(row)
                if cp in BLOCKING:
                    blocking_rows.append(row)

        rows.append({
            "font": alias,
            "embedded_name": candidate["name"],
            "embedded_name_matches_alias": candidate["name"] == alias,
            "mode": "GOLDEN_EXACT" if alias in EXCLUDED else "GOLDEN_APPEND_ONLY",
            "appended": appended,
            "glyphs": glyph_rows,
        })

    blockers = {key: value for key, value in totals.items() if key in {
        "raw_l8_sdf_floor_pixels", "unexpected_l8_changes", "dxt_baseline_byte_changes",
        "golden_owned_pixel_changes", "dxt_golden_block_collisions", "golden_index_changes",
        "golden_metric_changes", "golden_uv_changes", "embedded_name_mismatches"
    } and value}
    expected_blocking_rows = totals["appended_fonts"] * len(BLOCKING)
    if len(blocking_rows) != expected_blocking_rows or any(row["status"] != "PASS" for row in blocking_rows):
        blockers["blocking_glyph_failures"] = sum(row["status"] != "PASS" for row in blocking_rows)
    report = {
        "schema": "ams2-kr-068.1-appended-glyph-storage-validation-v1",
        "golden_root": str(args.golden_root.resolve()),
        "baseline_root": str(args.baseline_root.resolve()),
        "candidate_root": str(args.candidate_root.resolve()),
        "contract": "Golden records/pixels exact; DXT3 exact to v0.6.8; appended L8 only 120->0; 121..135 antialiasing preserved",
        "totals": totals, "blocking_glyphs": blocking_rows, "blockers": blockers,
        "fonts": rows, "status": "PASS" if not blockers else "BLOCK"
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "totals": totals, "blockers": blockers, "report": str(args.report.resolve())}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
