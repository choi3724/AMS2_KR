#!/usr/bin/env python3
"""Headless integration test using disposable output copies."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from asset_core import bgui_rows, build_single_font, edit_bgui_copy, edit_tdb_copy, tdb_rows
from ams2_asset_studio import (
    DEFAULT_BGUI_TOOL,
    DEFAULT_DDS_BUILDER,
    DEFAULT_FONT_TOOL,
    DEFAULT_PRETENDARD,
    DEFAULT_RELEASE,
    DEFAULT_TDB_TOOL,
)


def main() -> int:
    results = {}
    with tempfile.TemporaryDirectory(prefix="ams2-asset-studio-") as temp_name:
        temp = Path(temp_name)
        game_tdb = DEFAULT_RELEASE / "text" / "game.tdb"
        rows = tdb_rows(game_tdb, DEFAULT_TDB_TOOL)
        target = next(row for row in rows if row["key"] == "Game_MainMenu_AudioDeviceLower")
        tdb_result = edit_tdb_copy(
            game_tdb,
            temp / "game.test.tdb",
            DEFAULT_TDB_TOOL,
            {target["index"]: target["korean"] + " 테스트"},
        )
        results["tdb"] = {
            "status": tdb_result["status"],
            "changed_index_count": tdb_result["changed_index_count"],
        }

        main_bgui = DEFAULT_RELEASE / "GUI" / "menu_mainmenu_1_6.bgui"
        bgui = bgui_rows(main_bgui, DEFAULT_BGUI_TOOL)
        target_bgui = bgui[0]
        bgui_result = edit_bgui_copy(
            main_bgui,
            temp / "menu_mainmenu_1_6.test.bgui",
            DEFAULT_BGUI_TOOL,
            {
                target_bgui["ordinal"]: {
                    "x": target_bgui["x"] + 1.0,
                    "y": target_bgui["y"],
                    "width": target_bgui["width"],
                    "height": target_bgui["height"],
                    "font": target_bgui["font"],
                }
            },
        )
        results["bgui"] = {
            "status": bgui_result["status"],
            "edited_ordinals": bgui_result["edited_ordinals"],
        }

        font_result = build_single_font(
            DEFAULT_PRETENDARD,
            DEFAULT_RELEASE / "GUI" / "kr09_font_heading_bold.bfont",
            DEFAULT_RELEASE / "GUI" / "kr09_font_heading_bold_00.dds",
            temp / "font-test",
            "kr_studio_test",
            18,
            1.0,
            1.0,
            0,
            0,
            0,
            -1,
            "",
            DEFAULT_FONT_TOOL,
            DEFAULT_DDS_BUILDER,
        )
        results["font"] = {
            "status": font_result["status"],
            "glyph_count": font_result["glyph_count"],
            "atlas": font_result["atlas"],
        }

    print(json.dumps({"status": "PASS", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
