# AMS2-KR-066 작업 보고서

## 최종 판정

`PASS — CLOSED BETA 0.6.6 RELEASE READY`

Closed Beta 0.6.5를 먼저 동결·검증·커밋한 뒤, 0.6.6에서 서킷 국가/타입, 거리 context, 플레이어 누적 시간, 순정 AI 이름 및 누락 glyph를 처리했다. 최종 후보는 실제 Single Race 3개 클래스와 제거/복원/재설치 회귀 검증을 통과했다.

## PHASE 0 — v0.6.5 기준점

- Release ZIP: `AMS2 한국어 패치 CB 0.6.5.zip`
- SHA-256: `337B30D429CA182CC53253470836563DB1E449EA827D5294D2052D780BC7D703`
- Runtime: Main Menu 및 첫 Replay의 차량 위 ProfileName font PASS
- Restore: `RESTORED_EXACT`
- Reinstall: `INSTALLED_EXACT`
- Commit: `f6014fb4b6ffe743c20cbf859238e15d3882ab50`
- Subject: `v0.6.5 차량 위 이름 폰트 및 최신 번역 반영`

## 서킷 국가 및 타입

- 국가: 21/21 한국어화, 미해결 0
- 코스 타입: 5/5 한국어화, 미해결 0
- 국가 코드/flag identifier: 변경 0
- track metadata: 변경 0
- 고도 단위: 변경 0

## 거리 표시

원 작업서의 싱글 레이스 킬로미터 변환 목표는 사용자의 최신 명시 지시로 변경됐다.

- Single Player 상세: `거리(m)` + 원시 미터값. Runtime 예: `4312`
- Loading: `[DISTANCE] 킬로미터`
- Player Preferences/Favorites 누적 거리: `[DISTANCE] 킬로미터`
- Course Select 길이: 기존 킬로미터 표시 유지
- 고도: 미터 유지

단위 문자열만 바꾸는 잘못된 변환이나 전역 `m` 치환은 하지 않았다.

## Player Preferences

- `타임` → `차량 운행 시간`
- `[HH]시 [MM]분` → `[HH]시간 [MM]분`
- `[DD]일 [HH]시 [MM]분` → `[DD]일 [HH]시간 [MM]분`
- clock/time-of-day 값은 변경하지 않았다.

## 순정 AI 이름

- Authoritative source: `text/drivers.tdb`
- 전체 records: 4,201
- 고유 원문 이름: 2,701
- 한국어 음차: 2,701
- 미해결: 0
- 이름 외 semantic change: 0
- `Safety Car` → `세이프티카`
- `Safety Car Driver` → `세이프티카운전자`
- 실제 사용자 nickname: 변경 0

AMS2가 공백 뒤 이름을 첫 글자로 줄이는 동작 때문에, 실제 표시값은 전체 음차명을 공백 없는 한 token으로 기록했다. 따라서 `콘. 구솔` 같은 축약 대신 `콘스탄틴구솔`처럼 전체 이름이 보인다.

## Glyph 및 회색 배경 회귀

초기 전체 font 재생성 후보에서 회색 glyph cell 배경이 재발해 폐기했다. 최종 방법은 v0.6.5의 기존 1,344 glyph pixel/metrics를 byte-level 의미로 보존하고, AI 이름에 부족한 68개 한글 음절만 추가하는 것이다.

- 일반 UI font aliases: 46
- 기존 glyph/font: 1,344
- 추가 glyph/font: 68
- 최종 glyph/font: 1,412
- 기존 glyph metric mismatch: 0
- 기존 glyph pixel mismatch: 0
- AI name missing glyph: 0
- 실제 화면 회색 glyph 배경: 0
- 차량 전용 display font 변경: 0

## 실제 Runtime 검증

AI 이름 수용 검증은 Replay가 아니라 실제 Single Race로 수행했다.

1. GT3 G2
   - 실제 session list PASS
   - 실제 driving HUD PASS
2. Formula V10 Gen3(B)
   - 실제 session list PASS
   - 실제 driving HUD PASS
3. Formula Junior
   - 실제 driving HUD PASS

대표 10명 이상에서 전체 한국어 이름, `세이프티카`, human nickname `ENG-IceBlasT`, 별표 없음, 회색 배경 없음이 확인됐다. v0.6.5에서 검증한 차량 위 ProfileName font route는 그대로 유지됐다. 별도 Results 화면 캡처는 남기지 않았으나 `drivers.tdb` semantic diff와 46개 font glyph coverage는 PASS다.

## 핵심 빌드 결과

- `game.tdb`: `A5110C65582CC517CE09897DAC12D3BBA4572A219348FCC7A3591417A6FD5FBF`
- `general.tdb`: `B1785F373FB226BF82080487359A7922FCFF31FB9A89B68E754EA545477D6EA3`
- `drivers.tdb`: `8642FD6E468433812C012EA5C875CCBDA482380F52B6A8ABF23566EC04C467F2`
- `menu_mainmenu_1_6.bgui`: `34EFB86CF7DBFA7E4C657D75EA20193BABA528CA86B2C54F1256140782489653` (v0.6.5 byte-exact 유지)
- `IGPHASEHUD.bff`: `D1618BB1F6E09F53E8BB86F4A163C2934B91814F5F326670381C5496B3D7C398`
- direct payload files: 449

## 설치·복원·재설치

- 0.6.5 predecessor 감지: PASS
- 0.6.6 update install: `UPDATED_EXACT`
- Runtime: PASS
- Remove: `RESTORED_EXACT`
- 제거 후 상태: `0.6.5 버전이 설치되어 있습니다. 업데이트가 필요합니다.`
- Reinstall: `INSTALLED_EXACT`
- 최종 게임 상태: 0.6.6 설치 완료, 게임 프로세스 종료

## 금지 범위 불변

- BOOTFLOW 변경: 0
- PHYSICSPERSISTENT 변경: 0
- vehicle/track physics 생성: 0
- CRD/TRD/driveline post-processing: 0
- AMS2CM/dotnet helper: 0
- EXE/DLL/hook/injection: 0

## 남은 주의사항

- 2,701개의 음차는 자동 생성 후 collision/문자권 검사를 통과했지만, 개별 이름의 관용 표기는 향후 사용자 피드백으로 다듬을 수 있다.
- 별도 Results 화면 runtime 캡처는 차기 화면 전수 QA 때 추가할 수 있다.

## 다음 권장 작업

`AMS2-KR-067 — Results/Championship/Multiplayer까지 포함한 화면별 잔존 영어 및 AI 음차 관용 표기 QA`
