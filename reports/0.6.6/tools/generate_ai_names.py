#!/usr/bin/env python3
"""Build a checkpointed Korean display-name inventory for stock drivers.tdb."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WORK = Path(__file__).resolve().parent
SOURCE = WORK / "phase1-source-inventory" / "drivers-records.json"
OUT = WORK / "ai-names"
CACHE = OUT / "translation-cache.json"
ENDPOINT = "https://clients5.google.com/translate_a/t"

# Stable, commonly used Korean motorsport spellings and ordering-sensitive samples.
OVERRIDES = {
    "Rubens Barrichello": "루벤스 바리첼로",
    "Felipe Massa": "펠리페 마사",
    "Emerson Fittipaldi": "에메르손 피티팔디",
    "Nelson Piquet Jr": "넬슨 피케 주니어",
    "Takumi Shintani": "타쿠미 신타니",
    "Oliver Jarvis": "올리버 자비스",
    "Niklas Lutz": "니클라스 루츠",
    "Gabriel Casagrande": "가브리엘 카사그란데",
    "Henri Sanfer": "앙리 상페르",
    "Paulo de T.Marques": "파울루 지 티 마르케스",
    "PJ Miller": "피제이 밀러",
    "Jake Villain Sr": "제이크 빌런 시니어",
    "Valdinei Reis JR": "발지네이 헤이스 주니어",
    "Fred Jasinski": "프레드 야신스키",
    "CJ Riley": "씨제이 라일리",
    "F. Monteiro": "에프 몬테이루",
    "Scotty Prunes": "스코티 프룬스",
    "Scotty Prunes\r\n": "스코티 프룬스",
}


def compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if ch.isascii() and ch.isalnum())


def load_cache() -> dict[str, str]:
    if not CACHE.exists():
        return dict(OVERRIDES)
    data = json.loads(CACHE.read_text(encoding="utf-8"))
    data.update(OVERRIDES)
    return data


def save_cache(cache: dict[str, str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    temp = CACHE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(CACHE)


def translate_batch(names: list[str]) -> list[str]:
    params = {
        "client": "dict-chrome-ex",
        "sl": "en",
        "tl": "ko",
        "q": "\n".join(names),
    }
    request = Request(
        ENDPOINT + "?" + urlencode(params),
        headers={"User-Agent": "Mozilla/5.0 (AMS2 Korean localization QA)"},
    )
    with urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    if len(names) == 1:
        return [" ".join(data[0].splitlines()).strip()]
    values = data[0].splitlines()
    if len(values) != len(names):
        raise RuntimeError(f"batch cardinality mismatch: {len(names)} input, {len(values)} output")
    return [value.strip() for value in values]


def translate_resilient(names: list[str]) -> dict[str, str]:
    """Bisect batches whose translated output contains an unexpected newline."""
    try:
        return dict(zip(names, translate_batch(names)))
    except RuntimeError as exc:
        if "cardinality mismatch" not in str(exc) or len(names) == 1:
            raise
        middle = len(names) // 2
        result = translate_resilient(names[:middle])
        result.update(translate_resilient(names[middle:]))
        return result


def translate_all(names: list[str], batch_size: int) -> dict[str, str]:
    cache = load_cache()
    pending = [name for name in names if name not in cache]
    print(f"unique={len(names)} cached={len(names) - len(pending)} pending={len(pending)}", flush=True)
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        last_error = None
        for attempt in range(1, 6):
            try:
                values = translate_resilient(batch)
                cache.update(values)
                save_cache(cache)
                print(f"translated={min(offset + len(batch), len(pending))}/{len(pending)}", flush=True)
                time.sleep(0.15)
                break
            except Exception as exc:  # checkpointed retry path
                last_error = exc
                time.sleep(attempt * 2)
        else:
            raise RuntimeError(f"translation batch failed at {offset}: {last_error}")
    cache.update(OVERRIDES)
    save_cache(cache)
    return cache


def category(name: str) -> list[str]:
    tags = []
    if re.search(r"[^\x00-\x7f]", name):
        tags.append("ACCENT_OR_NON_ASCII")
    if "-" in name:
        tags.append("HYPHEN")
    if "'" in name or "’" in name:
        tags.append("APOSTROPHE")
    if re.search(r"(?:^|\s)[A-Z]\.(?:\s|$)", name):
        tags.append("INITIAL")
    if len(name.split()) >= 3:
        tags.append("COMPOUND_NAME")
    if re.search(r"\b(?:Jr|Sr|II|III|IV)\.?$", name, re.I):
        tags.append("SUFFIX")
    return tags


def runtime_display_name(original: str, korean: str) -> str:
    """Avoid AMS2's Latin-style `first initial + surname` abbreviation.

    The HUD splits driver names on ASCII whitespace.  Korean transliterations
    therefore need a single token so the full name is retained in compact
    standings widgets.  Safety-car labels are UI roles, not personal names.
    """
    if original == "Safety Car":
        return "세이프티카"
    if original == "Safety Car Driver":
        return "세이프티카운전자"
    return re.sub(r"\s+", "", korean)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    names = sorted({row["english"] for row in rows})
    cache = load_cache() if args.cache_only else translate_all(names, args.batch_size)
    if args.cache_only:
        save_cache(cache)
    missing = [name for name in names if name not in cache]
    if missing:
        raise RuntimeError(f"missing translations: {len(missing)}")

    inventory = []
    low = []
    for row in rows:
        name = row["english"]
        korean = cache[name].strip()
        display = runtime_display_name(name, korean)
        has_hangul = bool(re.search(r"[가-힣]", korean))
        has_latin = bool(re.search(r"[A-Za-z]", korean))
        confidence = "HIGH" if name in OVERRIDES else ("MEDIUM" if has_hangul and not has_latin else "LOW")
        name_parts = name.split()
        key_prefix = "Drivers_Name_" + compact(name)
        source_binding = row["key"][len(key_prefix):] if row["key"].startswith(key_prefix) else None
        record = {
            "source": "text/drivers.tdb",
            "class": None,
            "livery": None,
            "source_binding": source_binding or None,
            "tdb_index": row["index"],
            "tdb_key": row["key"],
            "original_full_name": name,
            "given_name": " ".join(name_parts[:-1]) if len(name_parts) > 1 else name,
            "surname": name_parts[-1] if len(name_parts) > 1 else None,
            "country": None,
            "korean_name": korean,
            "runtime_display_name": display,
            "transliteration_confidence": confidence,
            "notes": "; ".join(category(name)) or ("CURATED_OVERRIDE" if name in OVERRIDES else "AUTOMATED_NAME_CONTEXT_TRANSLITERATION"),
        }
        inventory.append(record)
        if confidence == "LOW":
            low.append(record)

    collisions = []
    by_korean: dict[str, set[str]] = {}
    for name in names:
        by_korean.setdefault(cache[name], set()).add(name)
    for korean, originals in sorted(by_korean.items()):
        if len(originals) > 1:
            collisions.append({"korean_name": korean, "original_names": sorted(originals)})

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stock-ai-driver-names.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = list(inventory[0])
    with (OUT / "stock-ai-driver-names.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(inventory)
    (OUT / "ai-name-collisions.json").write_text(json.dumps(collisions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "ai-name-low-confidence.json").write_text(json.dumps(low, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "record_count": len(rows),
        "unique_original_name_count": len(names),
        "translated_unique_name_count": len({name for name in names if cache.get(name)}),
        "confidence": dict(Counter(item["transliteration_confidence"] for item in inventory)),
        "low_confidence_record_count": len(low),
        "collision_count": len(collisions),
        "non_name_fields_modified": 0,
        "runtime_display_policy": "SINGLE_TOKEN_FULL_NAME_TO_AVOID_LATIN_INITIAL_ABBREVIATION",
        "safety_car_display_name": "세이프티카",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
