# AMS2 한국어 패치 Closed Beta 0.6.3 검증 보고서

최종 판정: **PASS — 0.6.3 배포 ZIP 생성 및 독립 검증 완료**

## 영문·숫자 폰트 폭

- 0.6.2보다 advance가 넓어진 영문·숫자 글리프: **0개**
- 한글 메트릭 변경: **0개**
- 일반 UI 영문·숫자: 기존 advance의 약 92% 수준
- HUD 영문: 약 86%, 숫자·구두점: 약 80%
- glyph raster, bearing, DDS atlas는 변경하지 않았다.
- `Fanatec Wheel Base`, `User Set 1`, `Project CARS 2`, `1920x1080 143Hz`, 날짜, 랩타임, HUD 숫자를 실제 화면에서 확인했으며 새 가로 잘림은 발견되지 않았다.

## 번역·표시 수정

- `game.tdb`, `pit.tdb`, `rac.tdb`에서 한국어 값 32건 수정
- 비한국어 값 변경 0건, key/hash 변경 0건, roundtrip parse PASS
- 레이스 요약의 `Dry/Wet Skill`, `Limited Setup` 표시를 각각 `건조/우천 실력`, `제한 셋업`으로 수정
- 피트 전략 편집의 inline label을 `서스펜션 전체 동일`, `브레이크 전체 동일`, `전체 수리 선택/해제`로 수정
- 오디오 도움말 레코드 364건 중 362건은 연결 또는 한국어 값이 확인됐다. 남은 2건은 참조 key 자체가 없는 upstream source-absent 항목이므로 불안전한 가상 binding을 넣지 않았다.

## 런타임

- 기존 0.6.2 Hotfix를 감지하고 업데이트: PASS
- 최종 설치 상태: `INSTALLED_EXACT`
- 설치된 `AMS2 Korean Launcher.exe`로 실행해 Main Menu 도달: PASS
- Options, Single Race 설정, 상대·규칙, HUD/HUD Beta, Pause, Pit strategy, Results, Multiplayer 화면군을 순회·캡처했다.

## Installer 업데이트 기능

- 시작 시 비차단 업데이트 확인과 `업데이트 확인` 버튼을 추가했다.
- GitHub latest release API를 조회하고 새 버전이면 release 페이지를 연다.
- 현재 저장소가 private이므로 외부 익명 사용자의 조회는 공개 release endpoint가 마련되기 전까지 동작하지 않는다. 네트워크 실패는 설치를 차단하지 않는다.

## 패키지 검증

- ZIP: `E:\AMS2_Korean_Work\releases\AMS2-Korean-Closed-Beta-0.6.3-Pretendard.zip`
- SHA-256: `A4A2A2E41AFC830523E5AB4D00AE42FE482C374F86DFCD4517C17A9181B7D188`
- 독립 clean extraction: PASS
- SHA256SUMS 452개: 452/452 PASS
- release manifest JSON parse: PASS
- physics/vehicles/tracks/PHYSICSPERSISTENT payload: 0개

