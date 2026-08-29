# AMS2 한국어 패치 CB 0.6.82

v0.6.82는 2026-08-28 17:49 KST 직전, 사용자가 정상 동작을 확인한 `candidate12`를 릴리스한 버전이다.

핵심 구성:

- v0.6.8 번역, AI 이름, `세이프티 카`
- candidate12 font payload 294개
- 차량 위 이름용 `GUI/kr13_driver_name_semibold.bfont`
- stock F967에서 patched D161로 전환하는 최소 `IGPHASEHUD.bff` patch
- 플레이어 목록과 nameplate의 신규 글리프 identity 및 회색 배경 수정

검증 결과:

- ZIP/SHA/manifest: PASS
- direct payload: 449/449 exact
- fonts: 294/294 candidate12 exact
- replay-time binary candidates: 0
- install → remove → predecessor exact → reinstall: PASS
- 최종 게임 상태: `INSTALLED_EXACT`

Replay/Session 시간 열 clipping은 알려진 문제로 남겼다. 실패한 수정은 포함하지 않았으며 분석과 실패 원인만 저장소에 보존했다.
