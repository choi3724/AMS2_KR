# AMS2-KR-068 — v0.6.8 Pretendard Golden Append Audit

## 판정

`PASS_WITH_NAMEPLATE_VISUAL_PENDING`

일반 UI 폰트 46종은 v0.6.5 Golden을 기준으로 기존 1,344개 글리프를 전혀 이동·재래스터화하지 않고, AI 이름에 필요한 한글 68자와 NBSP 1자만 추가했다. 전용/nameplate 계열 3종과 순정 `IGPHASEHUD.bff`는 byte-exact로 유지했다.

## PHASE 0 — v0.6.7 동결

- 시작 HEAD: `7fd060a94201631506a6ca9983a3dde5961e0172`
- origin/main: `dda9802ea37dda53aa6e2a3d03792df35cf5cf64`
- v0.6.7 본 커밋: `60a361ee4d1b68decf3dcb40d5e5d394ff02f2a4`
- 메타데이터 커밋: `f8df34e7c19edb8ab2f1f83e8fbf2d3046b44363`
- 제외된 debug/cache: `E:\AMS2_Korean_Work\local-debug\AMS2-KR-068-v067-excluded`
- PHASE 1 시작 전 working tree: clean

## Golden

- Golden commit: `f6014fb4b6ffe743c20cbf859238e15d3882ab50`
- Golden 폰트: 49 BFONT, 각 5 DDS page, 폰트당 1,344 glyph
- 일반 append 대상: 46
- byte-exact 유지 대상: `kr13_driver_name_semibold`, `kr13_font_data_list`, `kr13_font_heading_44`

## 회귀 원인과 수정

v0.6.6 전체 재생성 결과는 Golden 대비 기존 글리프 index 57,500건, UV 53,375건, page 4,876건을 바꿨다. 이런 전체 atlas 재배치는 BFONT/DDS가 서로 다른 세대에서 혼입될 때 다른 글자·사각 배경·거친 외곽선을 만들 수 있다.

v0.6.8은 Golden header/record/page를 입력으로 삼아 새 레코드를 맨 뒤에만 붙인다. 기존 DXT block과 겹치지 않는 Golden page 4의 미사용 block에 신규 픽셀만 기록하고, 모든 기존 레코드와 픽셀을 검증기로 byte/semantic 비교한다.

## AI 글리프

- drivers.tdb Korean 이름: 4,201
- 필요 codepoint: 508
- Golden 보유: 439
- 신규: 69 (한글 68 + NBSP)
- 일반 폰트별 append: 69
- build 후 누락: 0

## Golden 보존

- 비교 폰트: 46
- 비교 기존 글리프: 61,824
- index/metric/advance/bearing/UV/page/pixel 변경: 모두 0
- 회색 배경/halo/거친 외곽선 회귀: 모두 0
- 두 번의 build 294개 파일 SHA-256: 전부 일치

## Runtime

- Startup → Main Menu: PASS
- Options: PASS
- User Event / Session Setup: PASS
- Rules & Penalties: PASS
- 실제 Single Race / Race HUD: PASS
- 서로 다른 AI 표시 행 41개 확인: 깨짐 0, 공백 실패 0, 누락 0
- human nickname `ENG-IceBlasT`: 원문 유지 PASS
- `세이프티 카`: 띄어쓰기 포함 PASS
- 일반 텍스트 회색 사각 배경, halo, 거친 테두리: 관찰 0

## Nameplate

- `IGPHASEHUD.bff`: 순정 SHA `F967D1A322EB75AAD742CF21888D75DB0CA4CB407ACDEC72F14D32BD5351E7DA`
- dedicated nameplate 3개 폰트: v0.6.5 byte-exact
- 이번 버전의 전용 Pretendard nameplate POC: 미실시
- 판정: `NAMEPLATE_VISUAL_PENDING`

일반 HUD 폰트를 nameplate에 다시 연결하지 않았다. 이전에 정상성이 확인된 순정 route를 보존하는 것이 이번 font 안정화 범위의 안전한 결과다.

## Freeze 확인

- translation 파일 변경: 0
- 거리 formatter 변경: 없음
- `menu_mainmenu_1_6.bgui` SHA: `1903023E097EEE1DE04E9F7C3D6AC01B762CA4E2F2BFDC15D9E72F3464F9F948`
- live font payload: 산출물 294개와 SHA exact
- 게임 상태: 런타임 QA 후 종료

대형 산출물은 `E:\AMS2_Korean_Work\artifacts\AMS2-KR-068\fonts`, 두 번째 결정성 빌드는 `E:\AMS2_Korean_Work\local-debug\AMS2-KR-068-determinism-run2`에 보존했다.
