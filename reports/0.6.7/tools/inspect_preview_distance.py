from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(r"E:\AMS2_Korean_Work\AMS2")
SOURCE = Path(r"E:\SteamLibrary\steamapps\common\Automobilista 2\GUI\menu_mainmenu_1_6.bgui")
TOOL = Path(r"E:\AMS2_Korean_Work\tools\AMS2-KR-008\bgui\ams2_bgui_core.py")
OUT = REPO / "reports" / "0.6.7" / "preview-distance-bgui-records.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def row(record) -> dict:
    return {
        "ordinal": record.ordinal,
        "start": f"0x{record.start:X}",
        "local_id": record.local_id,
        "object_id": record.object_id,
        "position": record.position,
        "size": record.size,
        "clip_rect": record.clip_rect,
        "alignment_style_raw": record.alignment_style_raw,
        "text_reference": record.text_reference,
        "font": record.font,
        "flags": f"0x{record.flags:08X}",
    }


def main() -> int:
    bgui = load(TOOL, "ams2_preview_distance_bgui")
    data = SOURCE.read_bytes()
    records = bgui.parse_text_records(data)
    nodes = bgui.enumerate_named_nodes(data)
    references = (
        "VM-CustomEvent-TrackAndVehicleSelection-TrackEx-PreviewTrack_Length",
        "VM-CustomRace-TrackAndVehicleSelection-TrackEx-PreviewTrack_Length",
    )
    windows = []
    for reference in references:
        needle = bytes([len(reference)]) + reference.encode("utf-8")
        if data.count(needle) != 1:
            raise RuntimeError(f"expected one binding {reference!r}, got {data.count(needle)}")
        offset = data.index(needle)
        nearby_records = sorted(records, key=lambda record: abs(record.start - offset))[:20]
        nearby_nodes = sorted(nodes, key=lambda node: abs(node.start - offset))[:30]
        windows.append(
            {
                "reference": reference,
                "reference_offset": f"0x{offset:X}",
                "nearest_text_records": [row(record) for record in sorted(nearby_records, key=lambda record: record.start)],
                "nearest_named_nodes": [
                    {
                        "start": f"0x{node.start:X}",
                        "delta": node.start - offset,
                        "local_id": node.local_id,
                        "name": node.name,
                        "object_id": node.object_id,
                        "position": node.position,
                        "size": node.size,
                    }
                    for node in sorted(nearby_nodes, key=lambda node: node.start)
                ],
            }
        )
    report = {
        "schema": "ams2-kr-067-preview-distance-bgui-inspection-v1",
        "source": str(SOURCE),
        "text_record_count": len(records),
        "named_node_count": len(nodes),
        "windows": windows,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "target_count": len(windows), "output": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
