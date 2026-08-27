#!/usr/bin/env python3
import importlib.util
import json
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
BUILDER = Path(r"E:\AMS2_Korean_Work\AMS2\tools\AMS2-Asset-Studio\vendor\ams2_korean_font_builder.py")
FONT_ROOT = WORK / "release-v066" / "payload" / "direct" / "gui"
NAMES = WORK / "ai-names" / "stock-ai-driver-names.json"
OUT = WORK / "ai-names" / "ai-name-glyph-validation.json"

spec = importlib.util.spec_from_file_location("ams2_font_glyph_validation", BUILDER)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

required = sorted({ord(ch) for row in json.loads(NAMES.read_text(encoding="utf-8")) for ch in row["runtime_display_name"] if "가" <= ch <= "힣"})
fonts = sorted(
    f"{path.name}.bfont"
    for path in (WORK / "fonts-v066").iterdir()
    if path.is_dir()
)
rows = []
for name in fonts:
    path = FONT_ROOT / name
    parsed = module.parse_bfont(path.read_bytes(), str(path))
    missing = sorted(set(required) - set(parsed.codepoints))
    rows.append({
        "font": name,
        "font_glyph_count": parsed.glyph_count,
        "required_ai_hangul_syllables": len(required),
        "missing_count": len(missing),
        "missing": [{"codepoint": f"U+{value:04X}", "character": chr(value)} for value in missing],
        "status": "PASS" if not missing else "BLOCK",
    })
report = {"schema": "ams2-kr-066-ai-name-glyph-validation-v1", "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "BLOCK", "fonts": rows}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "fonts": [{"font": row["font"], "missing": row["missing_count"]} for row in rows]}, ensure_ascii=False))
