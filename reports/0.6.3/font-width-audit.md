# AMS2-KR-0.6.3 Latin and Numeric Font Width Audit

Verdict: **PASS**

- Latin/numeric advances wider than 0.6.2: **0**
- Hangul metric changes: **0**
- General UI floor: 92% of the 0.6.2 advance
- HUD floors: 86% Latin and 80% compact numeric/punctuation
- Glyph raster width, bearing, and DDS atlas are unchanged

| BFONT | Profile | Narrower | Equal | Wider | Minimum ratio |
|---|---:|---:|---:|---:|---:|
| kr08_font_data_list_value.bfont | GENERAL_LATIN_NUMERIC_92 | 190 | 32 | 0 | 0.8571 |
| kr09_font_data_list_label.bfont | GENERAL_LATIN_NUMERIC_92 | 190 | 32 | 0 | 0.8571 |
| kr09_font_heading.bfont | GENERAL_LATIN_NUMERIC_92 | 202 | 20 | 0 | 0.8571 |
| kr09_font_heading_black.bfont | GENERAL_LATIN_NUMERIC_92 | 202 | 20 | 0 | 0.8571 |
| kr09_font_heading_bold.bfont | GENERAL_LATIN_NUMERIC_92 | 202 | 20 | 0 | 0.8571 |
| kr13_font_hud_light.bfont | HUD_LATIN_86_NUMERIC_80 | 222 | 0 | 0 | 0.75 |
| kr13_font_hud_main.bfont | HUD_LATIN_86_NUMERIC_80 | 222 | 0 | 0 | 0.75 |
| kr13_phoenix_body_footnote.bfont | HUD_LATIN_86_NUMERIC_80 | 222 | 0 | 0 | 0.75 |
| kr13_phoenix_tab_title.bfont | HUD_LATIN_86_NUMERIC_80 | 218 | 4 | 0 | 0.75 |

## Runtime checks

- Long audio device name displays in full
- `Fanatec Wheel Base` and `User Set 1` display in full
- `1920x1080 143Hz`, date, lap time, and HUD numbers display in full
- No new horizontal clipping found in general UI or driving HUD

