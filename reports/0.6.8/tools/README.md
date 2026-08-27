# v0.6.8 Font Tools

- `ams2_golden_font_appender.py`: v0.6.5 Golden BFONT/DDS에 drivers.tdb 누락 글리프만 append하고 기존 글리프 불변성을 검증한다.
- `build_unified_ui_fonts.py --append-only`: 기존 builder entry point에서 append-only 모드로 위 도구를 호출한다.

대형 build 결과는 Git에 넣지 않는다. 최종 산출물은 `E:\AMS2_Korean_Work\artifacts\AMS2-KR-068\fonts`에 있다.
