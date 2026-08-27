# AMS2-KR-066 도구

이번 handoff에는 변경된 작업 도구만 포함한다.

- `generate_ai_names.py`: 순정 AI 원문 이름 inventory 및 한국어 음차 runtime 값 생성
- `build_phase1_content.py`: TDB 및 거리 표시 정책 빌드
- `build_unified_ui_fonts_v066.py`: 기존 1,344 glyph pixel/metrics를 보존하고 누락 AI 음절만 추가
- `validate_ai_glyphs.py`: 전체 일반 UI 폰트의 AI 이름 glyph coverage 검증
- `validate_font_regression.py`: 기존 glyph pixel/metrics 회귀 검증
- `assemble_v066_payload.py`: v0.6.5 predecessor 위 0.6.6 payload 조립

테스트용 GUI 입력 도구와 대형 raw 캡처 묶음은 배포/Handoff에서 제외했다.
