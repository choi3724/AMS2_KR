# AMS2 한국어 패치

Automobilista 2 비공식 한국어 패치 및 관련 제작 도구 저장소입니다.

## 최신 배포본

- 버전: Closed Beta 0.6.5
- 제작자: ENGIceBlasT
- 설치 후 게임은 `AMS2 Korean Launcher.exe` 또는 설치 과정에서 만든 바로가기로 실행합니다.
- 일반 실행과 VR 모드 실행은 각각 제공되는 바로가기를 사용합니다.
- 0.6.5는 이전 설치 버전을 감지하며, 새 버전 확인 버튼을 제공합니다.

배포 ZIP과 검증 자료는 `releases/0.6.5`, `reports/0.6.5`에서 확인할 수 있습니다.

## 0.6.5 핵심 변경

- `IGPHASEHUD.bff`의 `hud_infoabovecar.bgui`에서 차량 위 이름 `ProfileName` 폰트 경로만 Pretendard HUD 폰트로 변경
- 355개 BFF 엔트리 중 대상 1개만 수정하고 나머지 354개 엔트리는 byte/metadata 변경 없이 보존
- 최신 `game.tdb`, Main Menu 및 In-game Menu BGUI 반영
- 업데이트 설치, Main Menu, 첫 번째 Replay, 제거·순정 부팅·재설치 검증

## 제작 도구

`tools/AMS2-Asset-Studio`에는 BFONT/DDS 폰트 생성, BGUI 레이아웃 조정 및 TDB 문자열 편집을 위한 개발 도구가 들어 있습니다.

## 주의

- 비공식·코드 미서명 패치입니다.
- 현재 배포본은 특정 AMS2 빌드를 기준으로 제작되었습니다.
- 원본 게임 파일, 사용자 백업, 진단 로그 및 개인 환경 파일은 이 저장소에 포함하지 않습니다.
