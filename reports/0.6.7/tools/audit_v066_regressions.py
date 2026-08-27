from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(r"E:\AMS2_Korean_Work\AMS2")
V065 = Path(r"E:\AMS2_Korean_Work\releases\AMS2 한국어 패치 CB 0.6.5\payload\direct")
V066 = Path(r"E:\AMS2_Korean_Work\releases\AMS2 한국어 패치 CB 0.6.6\payload\direct")
LIVE = Path(r"E:\SteamLibrary\steamapps\common\Automobilista 2")
OUT = REPO / "reports" / "0.6.7" / "v066-semantic-regression-audit.json"
TDB_TOOL = REPO / "tools" / "AMS2-Asset-Studio" / "vendor" / "ams2_tdb_editor.py"
FONT_TOOL = REPO / "tools" / "AMS2-Asset-Studio" / "vendor" / "ams2_korean_font_builder.py"
V066_FONT_SCRIPT = REPO / "reports" / "0.6.6" / "tools" / "build_unified_ui_fonts_v066.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def korean_values(document):
    language = next(item for item in document.languages if item.name.casefold() == "korean")
    return language.values


def normalized_name(value: str) -> str:
    return value.replace("\u00a0", " ")


def audit_tdb(tdb, relative: str) -> dict:
    old_path = V065 / relative
    base_path = V066 / relative
    live_path = LIVE / relative
    old = tdb.parse_tdb(old_path)
    base = tdb.parse_tdb(base_path)
    live = tdb.parse_tdb(live_path)
    if old.keys != base.keys or base.keys != live.keys:
        raise RuntimeError(f"key layout changed for {relative}")
    old_values = korean_values(old)
    base_values = korean_values(base)
    live_values = korean_values(live)
    rows = []
    counts = {
        "v066_changed_records": 0,
        "preserved_exact": 0,
        "preserved_semantic_format_variant": 0,
        "reverted_to_v065": 0,
        "changed_after_v066": 0,
    }
    for index, (before, expected, actual) in enumerate(zip(old_values, base_values, live_values)):
        if before == expected:
            continue
        counts["v066_changed_records"] += 1
        if actual == expected:
            status = "PRESERVED_EXACT"
            counts["preserved_exact"] += 1
        elif relative.casefold() == "text/drivers.tdb" and normalized_name(actual) == normalized_name(expected):
            status = "PRESERVED_SEMANTIC_FORMAT_VARIANT"
            counts["preserved_semantic_format_variant"] += 1
        elif actual == before:
            status = "REVERTED_TO_V065"
            counts["reverted_to_v065"] += 1
        else:
            status = "CHANGED_AFTER_V066"
            counts["changed_after_v066"] += 1
        if status != "PRESERVED_EXACT" or len(rows) < 20:
            rows.append(
                {
                    "index": index,
                    "key": base.keys[index],
                    "v065": before,
                    "v066": expected,
                    "live": actual,
                    "status": status,
                }
            )
    return {
        "file": relative,
        "v065_sha256": sha256(old_path),
        "v066_sha256": sha256(base_path),
        "live_sha256": sha256(live_path),
        "counts": counts,
        "non_exact_or_sample_records": rows,
    }


def audit_fonts(builder, font_script) -> dict:
    old_root = V065 / "gui"
    base_root = V066 / "gui"
    live_root = LIVE / "GUI"
    aliases = sorted(path.stem for path in base_root.glob("kr*.bfont"))
    rows = []
    totals = {
        "font_aliases": len(aliases),
        "aliases_with_v066_additions": 0,
        "aliases_missing_v066_codepoints": 0,
        "missing_v066_codepoints_total": 0,
        "v065_common_metric_mismatches": 0,
        "v065_common_pixel_mismatches": 0,
    }
    for alias in aliases:
        old_path = old_root / f"{alias}.bfont"
        base_path = base_root / f"{alias}.bfont"
        live_path = live_root / f"{alias}.bfont"
        if not old_path.is_file() or not live_path.is_file():
            continue
        old_font = builder.parse_bfont(old_path.read_bytes(), str(old_path))
        base_font = builder.parse_bfont(base_path.read_bytes(), str(base_path))
        live_font = builder.parse_bfont(live_path.read_bytes(), str(live_path))
        additions = sorted(set(base_font.codepoints) - set(old_font.codepoints))
        missing = sorted(set(base_font.codepoints) - set(live_font.codepoints))
        if additions:
            totals["aliases_with_v066_additions"] += 1
        if missing:
            totals["aliases_missing_v066_codepoints"] += 1
            totals["missing_v066_codepoints_total"] += len(missing)

        old_glyphs = font_script.load_v065_glyphs(builder, old_root, alias)
        live_glyphs = font_script.load_v065_glyphs(builder, live_root, alias)
        common = sorted(set(old_glyphs) & set(live_glyphs))
        metric_mismatches = 0
        pixel_mismatches = 0
        for codepoint in common:
            left = old_glyphs[codepoint]
            right = live_glyphs[codepoint]
            if (left.left, left.mask.width, left.advance) != (right.left, right.mask.width, right.advance):
                metric_mismatches += 1
            if left.mask.size != right.mask.size or left.mask.tobytes() != right.mask.tobytes():
                pixel_mismatches += 1
        totals["v065_common_metric_mismatches"] += metric_mismatches
        totals["v065_common_pixel_mismatches"] += pixel_mismatches
        rows.append(
            {
                "alias": alias,
                "v065_glyph_count": old_font.glyph_count,
                "v066_glyph_count": base_font.glyph_count,
                "live_glyph_count": live_font.glyph_count,
                "v066_additions": len(additions),
                "missing_from_live": len(missing),
                "missing": [{"codepoint": f"U+{cp:04X}", "character": chr(cp)} for cp in missing],
                "nbsp_present": 0x00A0 in live_font.codepoints,
                "v065_common_glyphs": len(common),
                "v065_common_metric_mismatches": metric_mismatches,
                "v065_common_pixel_mismatches": pixel_mismatches,
            }
        )
    return {"totals": totals, "fonts": rows}


def main() -> int:
    tdb = load(TDB_TOOL, "ams2_v066_regression_tdb")
    builder = load(FONT_TOOL, "ams2_v066_regression_font")
    font_script = load(V066_FONT_SCRIPT, "ams2_v066_regression_generator")
    tdb_rows = [audit_tdb(tdb, relative) for relative in ("text/game.tdb", "text/general.tdb", "text/drivers.tdb")]
    fonts = audit_fonts(builder, font_script)
    reverted = sum(row["counts"]["reverted_to_v065"] for row in tdb_rows)
    missing = fonts["totals"]["missing_v066_codepoints_total"]
    report = {
        "schema": "ams2-kr-067-v066-semantic-regression-audit-v1",
        "status": "PASS" if reverted == 0 and missing == 0 else "BLOCK",
        "baseline": "Closed Beta 0.6.6 direct payload",
        "tdb": tdb_rows,
        "fonts": fonts,
        "summary": {
            "tdb_records_reverted_to_v065": reverted,
            "v066_font_codepoints_missing_from_live": missing,
            "note": "CHANGED_AFTER_V066 is reviewed separately as an intentional 0.6.7 edit.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], **report["summary"], "font_totals": fonts["totals"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
