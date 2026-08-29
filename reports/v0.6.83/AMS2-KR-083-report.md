# AMS2-KR-083 — v0.6.83 완료 보고서

## 1. 시작 기준점

- 기준 버전: `v0.6.82`
- 기준 커밋: `061885ea768554d717746b2419a9a28801366a75`
- 작업 브랜치: `release/v0.6.83`
- 정책: v0.6.82 게임 payload는 유지하고 인스톨러 UI와 설치·복구 레이어만 변경
- Replay 시간 열 clipping 수정: 포함하지 않음

## 2. UI 변경 요약

- 사용자가 최종 제공한 2172×724 배너를 그대로 사용했으며 좌하단에 `한글 패치 제작 : ENGIceBlasT`가 표시된다.
- 검정/적색 테마, 배너, 상태 카드, 경로, 설치 옵션, 7개 주요 동작, 로그의 정보 계층을 기준 시안과 동일하게 구성했다.
- 상태 카드의 방패 아이콘을 축소하고 상태 제목·설명 두 줄의 수직 정렬을 보정했다.
- 설치, 제거/복구, 상태 확인, 한국어로 실행, 진단 ZIP, 업데이트 확인, 닫기 및 자동 감지/찾기를 4배 해상도 PNG 버튼 자산으로 만들었다.
- 최종 버튼 글자는 실제 표시 기준 주 버튼 약 20px, 자동 감지/찾기 약 15px로 확대했다.
- 버튼 이미지와 상태 카드의 문자는 `Pretendard-Medium.otf`로 렌더링했으며 GDI+ `AntiAliasGridFit`과 고품질 축소를 사용했다.
- 100% DPI 실제 실행 화면은 `ui/installer-after-v0.6.83.png`에 보존했다.

## 3. 삭제/복구 구조 변경 요약

- 설치 직전 transaction backup과 영구 canonical stock backup을 분리했다.
- 관리 파일마다 상대 경로, 설치 전/후 크기 및 SHA-256, `modified`/`created` 역할을 `files.tsv`에 기록한다.
- 덮어쓴 파일은 canonical stock backup에서 복원하고 SHA-256을 재검증한다.
- 패치가 만든 파일은 소유권 ledger에 근거해 삭제하고 부재를 재검증한다.
- v0.6.82 등 선행 패치가 설치된 상태에서도 과거 install history를 따라 영문 원본까지 되감아 canonical backup을 구성한다.
- 사용자 수정 파일과 소유권이 확인되지 않은 바로가기는 임의로 덮어쓰거나 삭제하지 않는다.
- 패치 소유 바로가기는 바탕 화면, 시작 메뉴, 작업 표시줄에서 제거한다.
- 최종 상태는 `STOCK_ENGLISH`, `INSTALLED_EXACT`, `RESTORED_EXACT`, `UPDATE_AVAILABLE`, `MIXED_OR_INCOMPLETE`, `BACKUP_MISSING_OR_DAMAGED`, `MANUAL_CHANGES_DETECTED`로 구분한다.

## 4. 설치/제거/복원 검증 결과

- 실제 게임: `E:\SteamLibrary\steamapps\common\Automobilista 2`
- 실제 install → check → remove → check 순환: 3회
- 최종 상태: `RESTORED_EXACT`
- 복구 대상 ledger: 450개
  - 원본 복원 및 SHA 검증: 95개
  - 패치 생성 파일 제거 및 부재 검증: 355개
- 원본 SHA 불일치: 0
- 패치 생성 파일 잔존: 0
- 패치 소유 바로가기 잔존: 0
- `Pakfiles\IGPHASEHUD.bff`: `F967D1A322EB75AAD742CF21888D75DB0CA4CB407ACDEC72F14D32BD5351E7DA`
- `Pakfiles\BOOTFLOW.bff`: `2FE28D744F8DF0443FB290A10DAC52AA1308DE9389E776F0BD5F2BB8F03355B7`
- `Pakfiles\PHYSICSPERSISTENT.bff`: `39B720D1DC4CE529AC06AE10D0CF756E602ABD97772C5A24D7F31065C289C434`
- `PHYSICSPERSISTENT.bff-remove`: 없음
- AMS2CM, dotnet helper, Generated Bootfiles, physics post-processing: 0

## 5. 남은 한계/보류 이슈

- Replay/Session 시간값 우측 clipping은 v0.6.83 범위에서 제외했다.
- HUD/BGUI/BFF 진단 실험, 폰트 glyph, 번역 payload는 v0.6.82에서 변경하지 않았다.
- v0.6.82 direct payload 449개와 비교한 변경은 버전 문자열을 가진 일반/VR 런처 2개뿐이며 예상 밖 게임 payload 변경은 0개다.
- GitHub 표시 이름에는 Closed Beta를 유지하지만 GitHub Pre-release 플래그는 사용하지 않는다.

## 6. 최종 판정

`PASS — UI_REDIGNED_AND_ENGLISH_STOCK_RESTORE_VERIFIED`

## 7. 릴리즈 정책

- 태그: `v0.6.83`
- GitHub Release: `prerelease=false`, `Latest=true`
- 첨부 자산: `AMS2 한국어 패치 CB 0.6.83.zip` 하나만 사용
- 과거 버전 인스톨러는 v0.6.83 Release asset에 포함하지 않음
- 릴리즈 ZIP SHA-256: `E584220E32B67848C6531AA5AC84100AFE01E515874A2569493CF84F380EE683`
