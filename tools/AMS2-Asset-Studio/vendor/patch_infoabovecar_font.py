#!/usr/bin/env python3
"""Route the driving HUD opponent nameplate to its dedicated Pretendard font."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


OLD_FONT = b"gui\\kr13_phoenix_body_regular.bfont"
NEW_FONT = b"gui\\kr13_driver_name_semibold.bfont"
PROFILE_NAME = b"ProfileName"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source = args.input.resolve()
    target = args.output.resolve()
    report_path = args.report.resolve()
    data = source.read_bytes()

    if len(OLD_FONT) != len(NEW_FONT):
        raise RuntimeError("font routes must have equal byte length")
    if data.count(PROFILE_NAME) != 1:
        raise RuntimeError("expected exactly one ProfileName node")
    if data.count(OLD_FONT) != 1:
        raise RuntimeError("expected exactly one current ProfileName font route")
    if data.count(NEW_FONT) != 0:
        raise RuntimeError("dedicated nameplate font route already exists")

    profile_offset = data.index(PROFILE_NAME)
    font_offset = data.index(OLD_FONT)
    if not (profile_offset < font_offset < profile_offset + 256):
        raise RuntimeError("font route is not attached to the ProfileName node")

    patched = data[:font_offset] + NEW_FONT + data[font_offset + len(OLD_FONT) :]
    if len(patched) != len(data):
        raise RuntimeError("BGUI size changed")
    if patched.count(NEW_FONT) != 1 or patched.count(OLD_FONT) != 0:
        raise RuntimeError("font route replacement validation failed")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(patched)
    report = {
        "schema": "ams2-kr-064-infoabovecar-font-route-v1",
        "status": "PASS",
        "source": str(source),
        "output": str(target),
        "source_sha256": sha256(data),
        "output_sha256": sha256(patched),
        "bytes": len(data),
        "profile_name_offset": profile_offset,
        "font_offset": font_offset,
        "old_font": OLD_FONT.decode("ascii"),
        "new_font": NEW_FONT.decode("ascii"),
        "equal_length_replacement": True,
        "non_target_bytes_unchanged": (
            data[:font_offset] == patched[:font_offset]
            and data[font_offset + len(OLD_FONT) :] == patched[font_offset + len(NEW_FONT) :]
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
