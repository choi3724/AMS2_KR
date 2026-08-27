from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


WORK = Path(__file__).resolve().parent
BASE_GUI = Path(r"E:\AMS2_Korean_Work\releases\AMS2 한국어 패치 CB 0.6.5\payload\direct\gui")
BUILDER_PATH = Path(r"E:\AMS2_Korean_Work\AMS2\tools\AMS2-Asset-Studio\vendor\ams2_korean_font_builder.py")
FONT_SCRIPT = WORK / "build_unified_ui_fonts_v066.py"
def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    builder = load(BUILDER_PATH, "ams2_font_regression_builder")
    font_script = load(FONT_SCRIPT, "ams2_font_regression_generator")
    rows = []
    targets = sorted(path.name for path in (WORK / "fonts-v066").iterdir() if path.is_dir())
    for alias in targets:
        old_font = builder.parse_bfont((BASE_GUI / f"{alias}.bfont").read_bytes(), f"old {alias}")
        new_root = WORK / "fonts-v066" / alias
        new_font = builder.parse_bfont((new_root / f"{alias}.bfont").read_bytes(), f"new {alias}")
        old_glyphs = font_script.load_v065_glyphs(builder, BASE_GUI, alias)
        new_glyphs = font_script.load_v065_glyphs(builder, new_root, alias)
        common = sorted(set(old_glyphs) & set(new_glyphs))
        metric_mismatches = []
        pixel_mismatches = []
        for cp in common:
            old = old_glyphs[cp]
            new = new_glyphs[cp]
            if (old.left, old.mask.width, old.advance) != (new.left, new.mask.width, new.advance):
                metric_mismatches.append(cp)
            if old.mask.size != new.mask.size or old.mask.tobytes() != new.mask.tobytes():
                pixel_mismatches.append(cp)
        rows.append(
            {
                "alias": alias,
                "v065_glyphs": old_font.glyph_count,
                "v066_glyphs": new_font.glyph_count,
                "added_glyphs": new_font.glyph_count - old_font.glyph_count,
                "common_glyphs": len(common),
                "existing_metric_mismatches": len(metric_mismatches),
                "existing_pixel_mismatches": len(pixel_mismatches),
                "status": "PASS" if not metric_mismatches and not pixel_mismatches else "BLOCK",
            }
        )
    report = {
        "schema": "ams2-kr-066-v065-font-visual-regression-v1",
        "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "BLOCK",
        "policy": "PRESERVE_V065_EXISTING_GLYPH_PIXELS_AND_METRICS_ADD_ONLY_REQUIRED_AI_SYLLABLES",
        "fonts": rows,
    }
    output = WORK / "build-v066" / "font-regression-validation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
