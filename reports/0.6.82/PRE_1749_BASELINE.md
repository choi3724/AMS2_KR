# AMS2 한국어 패치 CB 0.6.82 기준점

## 기준 시각

- 2026-08-28 17:49 KST 직전
- 내부 후보: `AMS2-KR-068.1 candidate12`
- 사용자 런타임 확인: `정상동작확인함`

## 포함 상태

- v0.6.8의 번역 및 AI 드라이버 이름
- `세이프티 카` 표기
- candidate12 폰트 294개
- `Pakfiles/IGPHASEHUD.bff`의 최소 nameplate route 패치
- `ProfileName` → `GUI/kr13_driver_name_semibold.bfont`
- AI 이름의 `콧/밥/톨/앨` 글리프 identity 정상
- 플레이어 목록 및 차량 위 nameplate의 신규 글리프 회색 배경 제거

## 동결 해시

- candidate12 driver BFONT: `6409DA7DE921013C28357E59CC0F7FA85FC8954BB1BE0E47FB152120B5CDB958`
- patched `IGPHASEHUD.bff`: `D1618BB1F6E09F53E8BB86F4A163C2934B91814F5F326670381C5496B3D7C398`
- stock `IGPHASEHUD.bff`: `F967D1A322EB75AAD742CF21888D75DB0CA4CB407ACDEC72F14D32BD5351E7DA`
- drivers TDB: `9664012AFECEB259AC03522908112ADB451D51F5E9D9C99F605ED71815FAE810`

## 제외 상태

- 2026-08-28 17:49 KST 이후 시작한 Replay/Session 시간 열 clipping 후보
- replay 시간 Text object 좌표·폭 변경
- digit/period advance 변경
- 진단용 100px/200px 이동 BGUI/BFF
- replay 관련 임시 patcher와 runtime candidate

v0.6.82는 위 제외 항목을 적용하지 않는다.
