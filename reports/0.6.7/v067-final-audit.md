# v0.6.7 최종 감사

## 기준점

- predecessor: `7fd060a94201631506a6ca9983a3dde5961e0172` (`v0.6.6 서킷 정보 단위 및 AI 이름 한글화`)
- origin/main: `dda9802ea37dda53aa6e2a3d03792df35cf5cf64`
- local ahead/behind: `2/0`
- local history를 authoritative development history로 사용했으며 reset/rebase를 수행하지 않았다.

## 포함한 수정

- `menu_mainmenu_1_6.bgui`의 사용자 화면 fallback 한 곳을 `제한 셋업`에서 `셋업 제한`으로 변경했다.
- 출력 파일 크기는 동일하고 변경량은 8바이트다.
- v0.6.6 번역, 국가/서킷 타입, 프로필 통계, AI 이름 및 공백, `세이프티 카`가 유지되는지 정적·런타임 감사를 기록했다.
- 커스텀 nameplate route는 배포하지 않고 stock `IGPHASEHUD.bff`를 유지했다.

## 검증 결과

- TDB 의미 회귀: 0건
- v0.6.6 신규 AI 글리프 누락: 0
- 사용자 화면용 구번역 BGUI fallback: 0건
- live `menu_mainmenu_1_6.bgui` SHA-256: `1903023E097EEE1DE04E9F7C3D6AC01B762CA4E2F2BFDC15D9E72F3464F9F948`
- live stock `IGPHASEHUD.bff` SHA-256: `F967D1A322EB75AAD742CF21888D75DB0CA4CB407ACDEC72F14D32BD5351E7DA`
- 실제 레이스에서 AI 전체 이름/공백, human nickname, `세이프티 카`, 국가와 서킷 타입을 확인했다.

## 의도적으로 이관한 항목

- 싱글 레이스 미리보기의 raw meter formatter는 `PENDING_FORMATTER_PATH`다. v0.6.7에서 신규 구현하지 않았다.
- 일반 Pretendard Golden font 복원과 append-only AI glyph 증설은 v0.6.8 범위다.
- dedicated Pretendard nameplate는 stock route의 정확성을 우선하며 별도 POC로 남긴다.

## 제외한 항목

- 실패한 `safe-fonts` 실험 산출물
- 폐기된 custom nameplate builder 변경
- 중간 탐색 스크린샷 29개
- Python `__pycache__` 5개

제외 파일은 삭제하지 않고 `E:\AMS2_Korean_Work\local-debug\AMS2-KR-068-v067-excluded`에 격리했다.

## 판정

`PASS_V067_BASELINE_FREEZE`
