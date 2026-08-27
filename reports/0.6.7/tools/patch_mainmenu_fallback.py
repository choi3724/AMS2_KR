#!/usr/bin/env python3
"""Patch the one stale Limited Setup fallback in the v0.6.6 main-menu BGUI."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path


BASE_SHA256 = "34efb86cf7dbfa7e4c657d75ea20193baba528ca86b2c54f1256140782489653"
ENTRY_SUFFIX = "payload/direct/gui/menu_mainmenu_1_6.bgui"
OLD = "제한 셋업".encode("utf-16le")
NEW = "셋업 제한".encode("utf-16le")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} RELEASE_ZIP OUTPUT_DIR")

    archive, output_dir = map(Path, sys.argv[1:])
    with zipfile.ZipFile(archive) as zf:
        matches = [name for name in zf.namelist() if name.replace("\\", "/").endswith(ENTRY_SUFFIX)]
        assert len(matches) == 1, matches
        original = zf.read(matches[0])

    assert sha256(original) == BASE_SHA256
    assert original.count(OLD) == 1
    assert original.count(NEW) == 0

    patched = original.replace(OLD, NEW)
    assert len(patched) == len(original)
    assert sum(a != b for a, b in zip(original, patched)) == 8

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "menu_mainmenu_1_6.bgui"
    output_file.write_bytes(patched)
    (output_dir / "patch-validation.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "source_entry": matches[0],
                "source_sha256": sha256(original).upper(),
                "output_sha256": sha256(patched).upper(),
                "source_size": len(original),
                "output_size": len(patched),
                "changed_byte_count": sum(a != b for a, b in zip(original, patched)),
                "change": {"old": "제한 셋업", "new": "셋업 제한", "count": 1},
                "v067_experimental_object_renames_retained": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output_file)


if __name__ == "__main__":
    main()
