#!/usr/bin/env python3
"""Inspect the small IGPHASEHUD leaderboard BGUI files without menu-size assumptions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from ams2_bgui_editor import parse_resource_header, parse_text_records


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def named_nodes(data: bytes) -> list[dict]:
    """Return structurally plausible named GUI nodes for local context only."""
    nodes = []
    for name_offset in range(4, len(data) - 32):
        length = data[name_offset]
        if not 1 <= length <= 80:
            continue
        end = name_offset + 1 + length
        if end + 24 > len(data):
            continue
        raw = data[name_offset + 1 : end]
        try:
            name = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not name or any(ord(ch) < 0x20 for ch in name):
            continue
        local_id = struct.unpack_from("<I", data, name_offset - 4)[0]
        object_id = struct.unpack_from("<I", data, end + 4)[0]
        if local_id > 0xFFFF or object_id == 0 or object_id > 1_000_000:
            continue
        values = struct.unpack_from("<4f", data, end + 8)
        if not all(math.isfinite(value) and abs(value) <= 1.0e8 for value in values):
            continue
        nodes.append(
            {
                "start": name_offset - 4,
                "name": name,
                "local_id": local_id,
                "object_id": object_id,
                "position": [values[0], values[1]],
                "size": [values[2], values[3]],
            }
        )
    return nodes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    resources = []
    for path in args.input:
        data = path.read_bytes()
        header = parse_resource_header(data)
        records = parse_text_records(data)
        nodes = named_nodes(data)
        resources.append(
            {
                "path": str(path),
                "bytes": len(data),
                "sha256": sha256(data),
                "resource_count": header.count,
                "text_record_count": len(records),
                "named_nodes": nodes,
                "records": [
                    {
                        "ordinal": record.ordinal,
                        "start": f"0x{record.start:X}",
                        "local_id": record.local_id,
                        "object_id": record.object_id,
                        "position": list(record.position),
                        "size": list(record.size),
                        "field_f32_2": list(record.field_f32_2),
                        "clip_rect": list(record.clip_rect),
                        "alignment_style_raw": record.alignment_style_raw,
                        "text_reference": record.text_reference,
                        "text_reference_hash": f"0x{record.text_reference_hash:08X}",
                        "font": record.font,
                        "flags": f"0x{record.flags:08X}",
                        "nearest_preceding_nodes": [
                            node
                            for node in nodes
                            if 0 <= record.start - node["start"] <= 0x500
                        ][-12:],
                    }
                    for record in records
                ],
            }
        )

    report = {
        "schema": "ams2-kr-068.1-replay-time-layout-inspection-v1",
        "resources": resources,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "resources": len(resources), "records": sum(len(item["records"]) for item in resources)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
