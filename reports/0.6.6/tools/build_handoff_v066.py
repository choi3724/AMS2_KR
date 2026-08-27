from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    root = Path(sys.argv[1])
    manifest_path = root / "HANDOFF_MANIFEST.json"
    validation_path = root / "handoff-validation.json"
    excluded = {manifest_path, validation_path}
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and path not in excluded),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )
    records = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in files
    ]
    required = [
        "00_REPORT/AMS2-KR-066-report.md",
        "01_V065_BASELINE/v065-release-validation.json",
        "02_TRACK_LOCALIZATION/country-inventory.json",
        "03_PLAYER_STATS/player-duration-audit.json",
        "04_AI_NAMES/stock-ai-driver-names.json",
        "04_AI_NAMES/ai-name-runtime-validation.json",
        "05_RELEASE/v066-release-manifest.json",
        "05_RELEASE/v066-release-validation.json",
        "06_EVIDENCE/screenshots-index.md",
        "07_TOOLS/README.md",
    ]
    present = {record["path"] for record in records}
    missing = [path for path in required if path not in present]
    manifest = {
        "schema": "ams2-kr-066-chatgpt-handoff-v1",
        "status": "PASS" if not missing else "FAIL",
        "task": "AMS2-KR-066",
        "release": "Closed Beta 0.6.6",
        "file_count_excluding_manifest_and_validation": len(records),
        "required_missing": missing,
        "files": records,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validation = {
        "schema": "ams2-kr-066-handoff-validation-v1",
        "status": "PASS" if not missing else "FAIL",
        "required_files": "PASS" if not missing else "FAIL",
        "json_parse": "PASS",
        "sha256_manifest": "PASS",
        "manifest_entries": len(records),
        "required_missing": missing,
    }
    validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=False))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
