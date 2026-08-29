# Replay/Session 시간 열 clipping — 분석 보존 및 수정 이관

## 상태

`DEFERRED_ANALYSIS_ONLY`

v0.6.82에는 Replay/Session 시간 열의 실제 수정이 포함되지 않는다. 2026-08-28 17:49 KST 이후 생성한 BGUI/BFF 후보와 좌표·폭·폰트 metric 변경은 모두 릴리스에서 제외했다.

## 확인된 증상

- 리플레이/플레이어 목록 우측 시간값의 마지막 숫자가 상황에 따라 clipping됨.
- 정지, 스크롤 중, 스크롤 종료 후의 표시 폭이 일정하지 않음.
- 동일 문자열도 행 상태에 따라 clipping 정도가 달라 단순 고정 폭 부족만으로 설명되지 않음.

## 실패한 접근

1. 추정 Text object의 x/width를 미세 조정함.
2. 후보 object를 100px 이상 이동하는 강한 진단 변경을 적용함.
3. 그룹 단위 BGUI 후보 및 `IGPHASEHUD.bff` entry를 변경함.
4. 숫자·점 glyph 폭/advance 변경 가능성을 조사함.

결과: 실제 시간 열의 active runtime object를 화면에서 확정하지 못했거나, 기대한 이동이 나타나지 않았다. 일부 후보는 다른 HUD 상태에만 영향을 주었다. 따라서 좌표·폭·digit metric을 릴리스에 남기면 근거 없는 회귀가 된다.

## 보존한 분석 자료

- `replay-time-layout-inspection.json`
- `replay-time-state-variance-analysis.md`
- `replay-time-active-object-by-state.json`
- `replay-time-object-inventory.json`
- `replay-time-binding-analysis.json`
- `replay-time-layout-call-chain.json`
- `replay-time-clip-owner.json`
- `replay-time-glyph-bounds-analysis.json`
- `replay-time-screen-boundary-comparison.json`
- `replay-time-root-cause.json`
- `replay-time-render-pipeline-RCA.md`
- `replay-time-failed-candidates-matrix.json`

## 후속 작업의 시작 조건

미세 수정 전에 실제 시간 열을 100px 이상 이동하거나 사라지게 하는 runtime-visible proof로 active object를 먼저 확정해야 한다. 후보가 많으면 그룹 단위 이진 탐색을 사용한다. 증명 전에는 font 전체, 한글/영문 폭, 숫자/점 advance, 좌표 및 clipping 영역을 변경하지 않는다.

## v0.6.82 불변 조건

- replay 시간 BGUI 수정 0
- replay 시간 BFF 수정 0
- digit/period metric 수정 0
- candidate12 font 및 nameplate route만 유지
