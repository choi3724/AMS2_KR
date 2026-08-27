from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(r"E:\AMS2_Korean_Work\AMS2")
V065 = Path(r"E:\AMS2_Korean_Work\releases\AMS2 한국어 패치 CB 0.6.5\payload\direct")
V066 = Path(r"E:\AMS2_Korean_Work\releases\AMS2 한국어 패치 CB 0.6.6\payload\direct")
LIVE = Path(r"E:\SteamLibrary\steamapps\common\Automobilista 2")
TDB_TOOL = REPO / "tools" / "AMS2-Asset-Studio" / "vendor" / "ams2_tdb_editor.py"
OUT = REPO / "reports" / "0.6.7" / "v066-bgui-fallback-audit.json"

KNOWN_TECHNICAL_HITS = {
    "General_TrackDetails_USA": "Only _USA_ view-model tokens and STOCKUSA vehicle-display identifiers; not visible country fallback text.",
    "General_TrackDetails_Japan": "Only JapaneseBootFlow and JP-antipiracy resource identifiers; not visible country fallback text.",
    "General_TrackDetails_Rallycross": "Only RallycrossResultsTable and RallycrossTabMenu object identifiers; not visible localized label text.",
}


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def korean(document):
    return next(language for language in document.languages if language.name.casefold() == "korean")


def offsets(data: bytes, needle: bytes) -> list[int]:
    found: list[int] = []
    start = 0
    while True:
        offset = data.find(needle, start)
        if offset < 0:
            return found
        found.append(offset)
        start = offset + 1


def context(data: bytes, offset: int, needle_length: int, encoding: str) -> str:
    radius = 160 if encoding == "utf-8" else 320
    start = max(0, offset - radius)
    end = min(len(data), offset + needle_length + radius)
    if encoding == "utf-16le":
        start -= start % 2
        end -= end % 2
        decoded = data[start:end].decode("utf-16-le", errors="replace")
    else:
        decoded = data[start:end].decode("utf-8", errors="replace")
    return " ".join(decoded.replace("\x00", " ").split())


def search_bgui(value: str) -> list[dict]:
    if not value or len(value.strip()) < 2:
        return []
    encodings = {
        "utf-8": value.encode("utf-8"),
        "utf-16le": value.encode("utf-16-le"),
    }
    results: list[dict] = []
    for path in sorted((LIVE / "GUI").rglob("*.bgui")):
        data = path.read_bytes()
        for encoding, needle in encodings.items():
            hits = offsets(data, needle)
            if hits:
                results.append(
                    {
                        "file": str(path.relative_to(LIVE)),
                        "encoding": encoding,
                        "count": len(hits),
                        "offsets": [f"0x{offset:X}" for offset in hits[:20]],
                        "contexts": [context(data, offset, len(needle), encoding) for offset in hits[:5]],
                    }
                )
    return results


def changed_records(tdb, relative: str) -> list[dict]:
    old = tdb.parse_tdb(V065 / relative)
    new = tdb.parse_tdb(V066 / relative)
    old_values = korean(old).values
    new_values = korean(new).values
    rows: list[dict] = []
    common = min(len(old.keys), len(new.keys))
    for index in range(common):
        before = old_values[index]
        after = new_values[index]
        if before == after:
            continue
        old_hits = search_bgui(before)
        new_hits = search_bgui(after)
        rows.append(
            {
                "source_file": relative,
                "index": index,
                "key": new.keys[index],
                "v065": before,
                "v066": after,
                "old_value_bgui_hits": old_hits,
                "new_value_bgui_hits": new_hits,
                "candidate_stale_fallback": bool(old_hits and not new_hits),
            }
        )
    return rows


def main() -> int:
    tdb = load(TDB_TOOL, "ams2_v066_bgui_fallback_tdb")
    rows: list[dict] = []
    for relative in ("text/game.tdb", "text/general.tdb"):
        rows.extend(changed_records(tdb, relative))
    candidates = [row for row in rows if row["candidate_stale_fallback"]]
    for row in candidates:
        reason = KNOWN_TECHNICAL_HITS.get(row["key"])
        row["review"] = {
            "classification": "TECHNICAL_IDENTIFIER" if reason else "UNRESOLVED",
            "reason": reason or "Manual context review required.",
        }
    unresolved = [row for row in candidates if row["review"]["classification"] == "UNRESOLVED"]
    report = {
        "schema": "ams2-kr-067-v066-bgui-fallback-audit-v1",
        "status": "PASS" if not unresolved else "REVIEW",
        "scope": "All Korean values changed by 0.6.6 in game.tdb/general.tdb, searched byte-exact in every live BGUI",
        "changed_record_count": len(rows),
        "candidate_stale_fallback_count": len(candidates),
        "technical_identifier_count": len(candidates) - len(unresolved),
        "unresolved_visible_fallback_count": len(unresolved),
        "candidates": candidates,
        "all_changed_records": rows,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "changed_record_count", "candidate_stale_fallback_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
