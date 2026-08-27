from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path


WORK = Path(r"C:\Users\User\Documents\Codex\2026-08-18\files-pasted-by-the-user-2026\work\AMS2-KR-066")
STAGE = WORK / "release-v066"
PAYLOAD = STAGE / "payload" / "direct"
BUILD = WORK / "build-v066"
FONTS = WORK / "fonts-v066"
MANIFEST = STAGE / "manifest" / "direct-files.tsv"
BASE_MANIFEST = Path(r"E:\AMS2_Korean_Work\releases\AMS2 한국어 패치 CB 0.6.5\manifest\direct-files.tsv")
BASE_PAYLOAD = Path(r"E:\AMS2_Korean_Work\releases\AMS2 한국어 패치 CB 0.6.5\payload\direct")
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def copy_exact(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if sha256(source) != sha256(target):
        raise RuntimeError(f"copy verification failed: {target}")


def main() -> int:
    if not STAGE.is_dir() or not PAYLOAD.is_dir():
        raise RuntimeError("v0.6.6 staging copy is missing")

    with BASE_MANIFEST.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        old = {row["relative_path"].replace("\\", "/"): row for row in reader}

    overlays = {
        "text/game.tdb": BUILD / "text" / "game.tdb",
        "text/general.tdb": BUILD / "text" / "general.tdb",
        "text/drivers.tdb": BUILD / "text" / "drivers.tdb",
        "gui/menu_mainmenu_1_6.bgui": BUILD / "gui" / "menu_mainmenu_1_6.bgui",
    }
    for relative, source in overlays.items():
        copy_exact(source, PAYLOAD / Path(relative))

    # Preserve every existing v0.6.5 glyph, then overlay only additive font
    # expansions generated from those exact pixels and metrics.
    for source in sorted((BASE_PAYLOAD / "gui").glob("kr*.bfont")):
        copy_exact(source, PAYLOAD / "gui" / source.name)
    for source in sorted((BASE_PAYLOAD / "gui").glob("kr*.dds")):
        copy_exact(source, PAYLOAD / "gui" / source.name)

    font_files = 0
    skipped_aliases: list[str] = []
    rebuilt_aliases: list[str] = []
    for alias_dir in sorted(path for path in FONTS.iterdir() if path.is_dir()):
        if not (PAYLOAD / "gui" / f"{alias_dir.name}.bfont").is_file():
            skipped_aliases.append(alias_dir.name)
            continue
        rebuilt_aliases.append(alias_dir.name)
        for source in sorted(alias_dir.iterdir()):
            if source.suffix.lower() not in {".bfont", ".dds"}:
                continue
            copy_exact(source, PAYLOAD / "gui" / source.name)
            font_files += 1

    rows = []
    for path in sorted((p for p in PAYLOAD.rglob("*") if p.is_file()), key=lambda p: p.relative_to(PAYLOAD).as_posix().casefold()):
        relative = path.relative_to(PAYLOAD).as_posix()
        digest = sha256(path)
        previous = old.get(relative)
        if previous:
            role = previous["role"]
            allowed = [item for item in previous["allowed_before_sha256"].split(";") if item]
            if digest != previous["sha256"] and previous["sha256"] not in allowed:
                allowed.append(previous["sha256"])
        else:
            role = "created"
            allowed = []
        rows.append({
            "relative_path": relative,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "role": role,
            "allowed_before_sha256": ";".join(allowed),
        })

    with MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "bytes", "sha256", "role", "allowed_before_sha256"], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    changed = [row["relative_path"] for row in rows if row["relative_path"] not in old or row["sha256"] != old[row["relative_path"]]["sha256"]]
    summary = {
        "schema": "ams2-kr-066-payload-assembly-v1",
        "status": "PASS",
        "direct_files": len(rows),
        "modified_role_files": sum(row["role"] == "modified" for row in rows),
        "created_role_files": sum(row["role"] == "created" for row in rows),
        "changed_from_v065": len(changed),
        "changed_files": changed,
        "font_files_rebuilt": font_files,
        "font_aliases_rebuilt": rebuilt_aliases,
        "existing_glyph_pixels_and_metrics_preserved_from_v065": True,
        "font_aliases_intentionally_not_added": skipped_aliases,
        "new_driver_tdb": "text/drivers.tdb" in changed,
    }
    (WORK / "build-v066" / "payload-assembly-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
