#!/usr/bin/env python3
"""Apply the proven one-entry IGPHASEHUD nameplate font-route patch."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


BYTES = 9_597_262
SOURCE_SHA256 = "F967D1A322EB75AAD742CF21888D75DB0CA4CB407ACDEC72F14D32BD5351E7DA"
TARGET_SHA256 = "D1618BB1F6E09F53E8BB86F4A163C2934B91814F5F326670381C5496B3D7C398"
PATCH_BYTES = 2_054
PATCH_SHA256 = "53D939CA71A5FA917B29E8DB615FD443163840FBB9FC943A3B364D4F19F38715"
WRITES = ((0x3080, 0, 1), (0x3084, 1, 1), (0x3092, 2, 4), (0x8E9800, 6, 2048))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def require(path: Path, size: int, digest: str, label: str) -> bytes:
    data = path.read_bytes()
    actual = sha256(data)
    if len(data) != size or actual != digest:
        raise RuntimeError(
            f"{label} mismatch: bytes={len(data)} sha256={actual}; "
            f"expected bytes={size} sha256={digest}"
        )
    return data


def changed_ranges(before: bytes, after: bytes) -> list[dict[str, int]]:
    indices = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    ranges: list[dict[str, int]] = []
    if not indices:
        return ranges
    start = previous = indices[0]
    for index in indices[1:]:
        if index != previous + 1:
            ranges.append({"offset": start, "length": previous - start + 1})
            start = index
        previous = index
    ranges.append({"offset": start, "length": previous - start + 1})
    return ranges


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    target = args.target.resolve()
    patch_path = args.patch.resolve()
    backup = args.backup.resolve()
    report_path = args.report.resolve()

    source = require(target, BYTES, SOURCE_SHA256, "stock IGPHASEHUD")
    patch = require(patch_path, PATCH_BYTES, PATCH_SHA256, "entry patch")

    if backup.exists():
        require(backup, BYTES, SOURCE_SHA256, "existing stock backup")
    else:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, backup)
        require(backup, BYTES, SOURCE_SHA256, "new stock backup")

    candidate = bytearray(source)
    for target_offset, patch_offset, length in WRITES:
        candidate[target_offset : target_offset + length] = patch[patch_offset : patch_offset + length]
    candidate_bytes = bytes(candidate)
    candidate_sha = sha256(candidate_bytes)
    if candidate_sha != TARGET_SHA256:
        raise RuntimeError(f"patched candidate SHA mismatch: {candidate_sha}")

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=target.name + ".kr0681.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(candidate_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        require(temporary, BYTES, TARGET_SHA256, "temporary patched IGPHASEHUD")
        os.replace(temporary, target)
        require(target, BYTES, TARGET_SHA256, "live patched IGPHASEHUD")
    finally:
        temporary.unlink(missing_ok=True)

    ranges = changed_ranges(source, candidate_bytes)
    report = {
        "schema": "ams2-kr-068.1-igphasehud-minimal-patch-v1",
        "status": "PASS",
        "target": str(target),
        "backup": str(backup),
        "patch": str(patch_path),
        "bytes": BYTES,
        "source_sha256": SOURCE_SHA256,
        "patch_sha256": PATCH_SHA256,
        "target_sha256": TARGET_SHA256,
        "write_contract": [
            {"target_offset": target_offset, "patch_offset": patch_offset, "length": length}
            for target_offset, patch_offset, length in WRITES
        ],
        "changed_byte_count": sum(item["length"] for item in ranges),
        "changed_ranges": ranges,
        "other_bff_entries_changed": 0,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
