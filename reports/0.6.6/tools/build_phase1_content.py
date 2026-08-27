#!/usr/bin/env python3
"""Build and strictly validate AMS2-KR-066 Phase 1 content payloads."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path


WORK = Path(__file__).resolve().parent
FIXTURE = WORK / "tdb-fixture" / "text"
OUT = WORK / "build-v066"
TDB_TOOL = Path(r"E:\AMS2_Korean_Work\AMS2\tools\AMS2-Asset-Studio\vendor\ams2_tdb_editor.py")
BGUI_TOOL = Path(r"E:\AMS2_Korean_Work\AMS2\tools\AMS2-Asset-Studio\vendor\ams2_bgui_editor.py")
MAIN_BGUI = Path(r"E:\AMS2_Korean_Work\releases\AMS2 한국어 패치 CB 0.6.5\payload\direct\gui\menu_mainmenu_1_6.bgui")
AI_CACHE = WORK / "ai-names" / "translation-cache.json"
AI_INVENTORY = WORK / "ai-names" / "stock-ai-driver-names.json"
TOKEN_RE = re.compile(r"\[[A-Z]+\]")
MASK32 = 0xFFFFFFFF


GAME_EDITS = {
    "Game_MainMenu_Time2": "차량 운행 시간",
    "Game_TimeDateCurrency_PlayTimeFormatDDHHMM": "[DD]일 [HH]시간 [MM]분",
    "Game_TimeDateCurrency_PlayTimeFormatHHMM": "[HH]시간 [MM]분",
    "Game_TimeDateCurrency_DistanceKMFormat": "[DISTANCE] 킬로미터",
}

GENERAL_EDITS = {
    "General_TimeDateCurrency_PlayTimeFormatDDHHMM": "[DD]일 [HH]시간 [MM]분",
    "General_TimeDateCurrency_PlayTimeFormatHHMM": "[HH]시간 [MM]분",
    "General_TimeDateCurrency_DistanceKMFormat": "[DISTANCE] 킬로미터",
    "General_TrackDetails_Argentina": "아르헨티나",
    "General_TrackDetails_Australia": "호주",
    "General_TrackDetails_Austria": "오스트리아",
    "General_TrackDetails_Belgium": "벨기에",
    "General_TrackDetails_Brazil": "브라질",
    "General_TrackDetails_Canada": "캐나다",
    "General_TrackDetails_Circuit": "서킷",
    "General_TrackDetails_Ecuador": "에콰도르",
    "General_TrackDetails_England": "영국",
    "General_TrackDetails_Finland": "핀란드",
    "General_TrackDetails_France": "프랑스",
    "General_TrackDetails_Germany": "독일",
    "General_TrackDetails_Hungary": "헝가리",
    "General_TrackDetails_Italy": "이탈리아",
    "General_TrackDetails_Japan": "일본",
    "General_TrackDetails_Kart": "카트 서킷",
    "General_TrackDetails_Monaco": "모나코",
    "General_TrackDetails_Norway": "노르웨이",
    "General_TrackDetails_Oval": "오벌",
    "General_TrackDetails_PointToPoint": "포인트 투 포인트",
    "General_TrackDetails_Portugal": "포르투갈",
    "General_TrackDetails_Rallycross": "랠리크로스",
    "General_TrackDetails_SouthAfrica": "남아프리카 공화국",
    "General_TrackDetails_Spain": "스페인",
    "General_TrackDetails_Turkey": "튀르키예",
    "General_TrackDetails_USA": "미국",
}

ADDED_ENGLISH = {
    "General_TrackDetails_Argentina": "Argentina",
    "General_TrackDetails_Brazil": "Brazil",
    "General_TrackDetails_Ecuador": "Ecuador",
    "General_TrackDetails_Finland": "Finland",
    "General_TrackDetails_Hungary": "Hungary",
    "General_TrackDetails_Monaco": "Monaco",
    "General_TrackDetails_Turkey": "Turkey",
}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def u32(value: int) -> int:
    return value & MASK32


def mix32(a: int, b: int, c: int) -> tuple[int, int, int]:
    a = u32(a - b); a = u32(a - c); a = u32(a ^ (c >> 13))
    b = u32(b - c); b = u32(b - a); b = u32(b ^ (a << 8))
    c = u32(c - a); c = u32(c - b); c = u32(c ^ (b >> 13))
    a = u32(a - b); a = u32(a - c); a = u32(a ^ (c >> 12))
    b = u32(b - c); b = u32(b - a); b = u32(b ^ (a << 16))
    c = u32(c - a); c = u32(c - b); c = u32(c ^ (b >> 5))
    a = u32(a - b); a = u32(a - c); a = u32(a ^ (c >> 3))
    b = u32(b - c); b = u32(b - a); b = u32(b ^ (a << 10))
    c = u32(c - a); c = u32(c - b); c = u32(c ^ (b >> 15))
    return a, b, c


def hash32_nocase(value: str) -> int:
    if not value:
        return 0xBD49D10D
    chars = value.upper()
    length = remaining = len(chars)
    offset = 0
    a = b = 0x9E3779B9
    c = 0
    while remaining >= 12:
        k = chars[offset : offset + 12]
        a = u32(a + ord(k[3]) + (ord(k[2]) << 8) + (ord(k[1]) << 16) + (ord(k[0]) << 24))
        b = u32(b + ord(k[7]) + (ord(k[6]) << 8) + (ord(k[5]) << 16) + (ord(k[4]) << 24))
        c = u32(c + ord(k[11]) + (ord(k[10]) << 8) + (ord(k[9]) << 16) + (ord(k[8]) << 24))
        a, b, c = mix32(a, b, c)
        offset += 12
        remaining -= 12
    tail = chars[offset:]
    c = u32(c + length)
    shifts = {
        11: ("c", 10, 24), 10: ("c", 9, 16), 9: ("c", 8, 8),
        8: ("b", 7, 24), 7: ("b", 6, 16), 6: ("b", 5, 8), 5: ("b", 4, 0),
        4: ("a", 3, 24), 3: ("a", 2, 16), 2: ("a", 1, 8), 1: ("a", 0, 0),
    }
    while remaining:
        target, index, shift = shifts[remaining]
        if target == "a": a = u32(a + (ord(tail[index]) << shift))
        elif target == "b": b = u32(b + (ord(tail[index]) << shift))
        else: c = u32(c + (ord(tail[index]) << shift))
        remaining -= 1
    return mix32(a, b, c)[2]


def recalc(document) -> None:
    document.key_count = len(document.keys)
    document.key_string_bytes_with_nuls = sum(len(key.encode("utf-8")) + 1 for key in document.keys)
    document.max_language_value_bytes_with_nuls = max(
        sum(len(value.encode("utf-16-le")) + 2 for value in language.values)
        for language in document.languages
    )


def patch_tdb(tdb, source: Path, output: Path, edits: dict[str, str], additions: dict[str, str] | None = None):
    before = tdb.parse_tdb(source)
    after = copy.deepcopy(before)
    korean = after.language("Korean")
    changes = []
    additions = additions or {}
    for key, value in edits.items():
        if key not in after.keys:
            if key not in additions:
                raise RuntimeError(f"missing TDB key without approved addition: {key}")
            continue
        index = after.keys.index(key)
        old = korean.values[index]
        if Counter(TOKEN_RE.findall(old)) != Counter(TOKEN_RE.findall(value)):
            raise RuntimeError(f"placeholder mismatch: {key}: {old!r} -> {value!r}")
        if old == value:
            raise RuntimeError(f"unexpected no-op: {key}")
        korean.values[index] = value
        changes.append({"key": key, "index": index, "before": old, "after": value})

    group_hash = hash32_nocase("TrackDetails")
    existing_hashes = set(after.language("English").hashes)
    added = []
    for key, english_value in additions.items():
        if key in after.keys:
            raise RuntimeError(f"approved added key already exists: {key}")
        record_hash = (group_hash << 32) | hash32_nocase(key)
        if record_hash in existing_hashes:
            raise RuntimeError(f"hash collision: {key}")
        existing_hashes.add(record_hash)
        after.keys.append(key)
        for language in after.languages:
            language.hashes.append(record_hash)
            language.values.append(edits[key] if language.name == "Korean" else english_value)
        added.append({"key": key, "hash": f"0x{record_hash:016X}", "english": english_value, "korean": edits[key]})
    recalc(after)
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = tdb.serialize_tdb(after)
    output.write_bytes(raw)
    reparsed = tdb.parse_tdb(output)
    if tdb.serialize_tdb(reparsed) != raw:
        raise RuntimeError(f"unstable TDB round trip: {output.name}")
    expected = [{"index": row["index"], "old_korean": row["before"], "new_korean": row["after"]} for row in changes]
    diff = tdb.semantic_diff(before, reparsed, expected)
    # Appended records are deliberately outside semantic_diff's same-shape contract.
    if not added and diff["status"] != "PASS":
        raise RuntimeError(f"semantic diff failed: {output.name}")
    if added:
        if reparsed.keys[:before.key_count] != before.keys:
            raise RuntimeError("existing key order changed while appending country keys")
        for language in before.languages:
            target = reparsed.language(language.name)
            expected_values = list(language.values)
            if language.name == "Korean":
                for row in changes:
                    expected_values[row["index"]] = row["after"]
            if target.hashes[:before.key_count] != language.hashes or target.values[:before.key_count] != expected_values:
                raise RuntimeError(f"unexpected existing record mutation: {language.name}")
    return {
        "source": str(source), "output": str(output),
        "source_sha256": sha256(source), "output_sha256": sha256(output),
        "changed_korean_values": changes, "added_records": added,
        "non_korean_existing_value_changes": 0, "existing_hash_changes": 0,
        "strict_roundtrip": "PASS",
    }


def patch_drivers(tdb, source: Path, output: Path):
    inventory = json.loads(AI_INVENTORY.read_text(encoding="utf-8"))
    display_by_original = {}
    for row in inventory:
        original = row["original_full_name"]
        display = row["runtime_display_name"]
        previous = display_by_original.setdefault(original, display)
        if previous != display:
            raise RuntimeError(f"inconsistent runtime display name: {original!r}")
    before = tdb.parse_tdb(source)
    after = copy.deepcopy(before)
    english = after.language("English")
    korean = after.language("Korean")
    changes = []
    for index, name in enumerate(english.values):
        value = display_by_original.get(name)
        if not value or not re.search(r"[가-힣]", value) or re.search(r"[A-Za-z]", value):
            raise RuntimeError(f"invalid Korean driver display name at {index}: {name!r} -> {value!r}")
        old = korean.values[index]
        korean.values[index] = value
        if old != value:
            changes.append({"key": before.keys[index], "index": index, "before": old, "after": value})
    recalc(after)
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = tdb.serialize_tdb(after)
    output.write_bytes(raw)
    reparsed = tdb.parse_tdb(output)
    if tdb.serialize_tdb(reparsed) != raw:
        raise RuntimeError("drivers.tdb unstable round trip")
    diff = tdb.semantic_diff(before, reparsed, [
        {"index": row["index"], "old_korean": row["before"], "new_korean": row["after"]}
        for row in changes
    ])
    if diff["status"] != "PASS":
        raise RuntimeError("drivers.tdb semantic diff failed")
    return {
        "source": str(source), "output": str(output),
        "source_sha256": sha256(source), "output_sha256": sha256(output),
        "record_count": before.key_count, "korean_name_value_changes": len(changes),
        "unique_original_names": len(set(english.values)),
        "non_name_semantic_changes": 0, "strict_roundtrip": "PASS",
    }


def replace_lp_text_record(
    data: bytes,
    old_reference: str,
    new_reference: str,
    new_reference_hash: int,
    old_name: str,
    new_name: str,
    new_name_hash: int,
) -> tuple[bytes, int]:
    old_raw = old_reference.encode("utf-8")
    new_raw = new_reference.encode("utf-8")
    old_name_raw = old_name.encode("utf-8")
    new_name_raw = new_name.encode("utf-8")
    if len(new_raw) > 255 or len(new_name_raw) > 255:
        raise RuntimeError("replacement too long")
    needle = bytes([len(old_raw)]) + old_raw
    count = data.count(needle)
    if count != 1:
        raise RuntimeError(f"expected one LP string {old_reference!r}, got {count}")
    text_offset = data.index(needle)
    start = text_offset - (69 + len(old_name_raw))
    old_name_marker = bytes([len(old_name_raw)]) + old_name_raw
    if data[start + 4 : start + 4 + len(old_name_marker)] != old_name_marker:
        raise RuntimeError(f"target text record is not named {old_name!r}")
    old_name_hash_end = start + 4 + len(old_name_marker) + 4
    geometry = data[old_name_hash_end:text_offset]
    if len(geometry) != 60:
        raise RuntimeError(f"unexpected text record geometry length: {len(geometry)}")
    replacement = (
        bytes([len(new_name_raw)])
        + new_name_raw
        + new_name_hash.to_bytes(4, "little")
        + geometry
        + bytes([len(new_raw)])
        + new_raw
        + new_reference_hash.to_bytes(4, "little")
    )
    old_hash_end = text_offset + len(needle) + 4
    return data[: start + 4] + replacement + data[old_hash_end:], count


def patch_main_bgui(bgui, source: Path, output: Path):
    raw = source.read_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    parsed = bgui.load_parsed(output)
    if not parsed.text_records:
        raise RuntimeError("copied BGUI parser returned no text records")
    originals = (
        "VM-CustomEvent-TrackAndVehicleSelection-TrackEx-PreviewTrack_Length",
        "VM-CustomRace-TrackAndVehicleSelection-TrackEx-PreviewTrack_Length",
    )
    for reference in originals:
        if raw.count(bytes([len(reference)]) + reference.encode("utf-8")) != 1:
            raise RuntimeError(f"raw metre binding changed: {reference}")
    return {
        "source": str(source), "output": str(output),
        "source_sha256": sha256(source), "output_sha256": sha256(output),
        "edits": [], "parser": "PASS", "text_record_count": len(parsed.text_records),
        "purpose": "Preserve the raw PreviewTrack_Length metre value; unit is shown by the Korean 거리(m) label",
    }


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite output: {OUT}")
    tdb = load_module(TDB_TOOL, "ams2_tdb_phase1_builder")
    bgui = load_module(BGUI_TOOL, "ams2_bgui_phase1_builder")
    reports = {
        "game.tdb": patch_tdb(tdb, FIXTURE / "game.tdb", OUT / "text" / "game.tdb", GAME_EDITS),
        "general.tdb": patch_tdb(tdb, FIXTURE / "general.tdb", OUT / "text" / "general.tdb", GENERAL_EDITS, ADDED_ENGLISH),
        "drivers.tdb": patch_drivers(tdb, FIXTURE / "drivers.tdb", OUT / "text" / "drivers.tdb"),
        "menu_mainmenu_1_6.bgui": patch_main_bgui(bgui, MAIN_BGUI, OUT / "gui" / "menu_mainmenu_1_6.bgui"),
    }
    manifest = {
        "schema": "ams2-kr-066-phase1-content-build-v1",
        "status": "PASS",
        "files": reports,
        "track_metadata_modified": False,
        "track_length_source_modified": False,
        "altitude_unit_modified": False,
        "ai_fields_modified_outside_korean_display_name": 0,
    }
    (OUT / "build-validation.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(OUT), "files": {key: value["output_sha256"] for key, value in reports.items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
