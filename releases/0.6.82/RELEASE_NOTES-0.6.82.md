# AMS2 한국어 패치 Closed Beta 0.6.82

- 2026-08-28 17:49 KST 직전의 runtime-confirmed candidate12를 릴리스 기준점으로 사용했습니다.
- AI 이름용 한글 68자와 `콧/밥/톨/앨` glyph identity를 보존했습니다.
- 플레이어 목록과 차량 위 nameplate의 신규 글리프 회색 배경을 제거했습니다.
- `IGPHASEHUD.bff`의 `ProfileName`만 `GUI/kr13_driver_name_semibold.bfont`로 연결합니다.
- 기존 v0.6.8의 번역, AI 이름 및 `세이프티 카` 표기를 포함합니다.

## 알려진 문제

- 일부 Replay/Session 시간값의 마지막 숫자가 잘릴 수 있습니다.
- 해당 문제의 분석과 실패 실험 기록은 저장소에 보존했지만, 실패한 BGUI/BFF/폰트 수정은 이 패키지에 포함하지 않았습니다.

본 패치는 Steam public build 24132163 기준으로 최적화되어 있습니다.