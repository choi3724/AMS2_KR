# AMS2 Font / Layout / Text Studio

AMS2 한국어 UI 자산을 한 곳에서 편집하는 개발용 도구다. 입력 파일을 직접 덮어쓰지 않고 사용자가 지정한 새 BFONT/DDS, BGUI, TDB만 생성한다.

## 실행

`Start-AMS2-Asset-Studio.cmd`를 실행한다.

현재 개발 PC에서는 Codex 번들 Python과 Pillow/NumPy를 자동으로 사용한다. 다른 PC에 복사할 때는 Python 3, Pillow, NumPy가 필요하며, 도구 폴더 아래 `runtime\python\pythonw.exe`를 두면 그 런타임을 우선 사용한다. BGUI/TDB/BFONT/DDS parser와 기본 Pretendard Medium 원본은 `vendor`, `assets` 아래에 함께 들어 있다.

## 기능

### 폰트 생성

- TTF/OTF에서 AMS2 BFONT/DDS 생성
- 픽셀 크기 지정
- 글리프 가로/세로 배율 지정
- X bearing, Y glyph 위치 조절
- line height와 baseline 조절
- 기준 BFONT 문자 집합에 새 문자 추가
- 새 alias로 폰트 추가
- 생성 후 BFONT round-trip, 글리프 누락, SHA-256 manifest 검증

기준 BFONT와 `_00.dds`는 출력 포맷과 AMS2 코드포인트 계약을 제공한다. 일반 UI 폰트만 대상으로 사용하고 아이콘/차량 LCD 전용 폰트에는 적용하지 않는다.

### BGUI 레이아웃/폰트

- 모든 Text 레코드 검색
- 선택 Text의 BFONT 경로 교체
- X/Y 위치, 텍스트 박스 폭/높이 조절
- 여러 Text 레코드에 동일 변경 적용
- 새 BGUI 저장 후 재파싱 검증

새 폰트를 BGUI에 연결할 때는 `gui\새_alias.bfont`처럼 입력한다. BFONT/DDS 파일도 최종 payload의 `GUI`에 함께 포함해야 한다.

### TDB 텍스트

- key/group/English/Korean 검색
- Korean 값 변경
- 새 TDB 저장
- English 및 다른 언어 block 불변 검증

일반 UI 문구는 BGUI 내부 문자열보다 TDB key로 관리되는 경우가 대부분이므로 텍스트 변경은 이 탭을 우선 사용한다.

## 안전 제한

- 입력 파일과 같은 경로로 저장할 수 없다.
- 이미 존재하는 출력 파일/폴더는 덮어쓰지 않는다.
- 게임 폴더 설치 기능은 없다.
- BGUI inline literal의 가변 길이 편집은 지원하지 않는다. TDB 문구 편집과 BGUI font/geometry만 지원한다.
- 실제 게임에 적용하기 전 생성 manifest와 별도 staging copy에서 검증한다.

## 자체 검사

```powershell
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\ams2_asset_studio.py --self-test
```

`PASS`와 BGUI/TDB 레코드 수가 출력되면 parser 및 기본 경로가 정상이다.

## 0.7 UI 수정 테스트

`build_ui_hotfix.py --release-root <0.7 배포 폴더> --output <새 외부 폴더>`는
리플레이 안내 2개와 세이프티 카 이름 3개만 수정한 `0.7-test3` 후보를 만든다.
세이프티 카 표기는 사용자 요청에 따라 일반 공백(U+0020)을 넣은 `세이프티 카`다.
입력 SHA-256을 고정하여 다른 버전이나 이미 수정된 파일의 재사용을 거부한다.
`0.7-test1`은 실제 게임 시작 시 충돌하여 원복했고 재적용을 차단했다.
텍스트 수정 생성기에서는 메뉴 객체 추가 코드를 제거했다.
제작자 표기 후보 `0.7-menu-footer2`도 실제 게임 시작 시 충돌하여 원복했다.
객체 계층 등록을 보완하고 정적 검사를 통과했어도 런타임 안전성은 확보되지 않았다.
실패한 메뉴 생성기는 저장소에서 제거하고 외부 오류 기록 폴더에 보존했다.
현재 메뉴 객체 추가 후보의 재적용은 모두 차단한다.

`test_ui_hotfix.ps1 -CandidateDir <후보> -ReleaseRoot <0.7 배포> -OutputRoot <외부 검사 폴더>`로
가상 게임 폴더에서 적용·원복과 수동 수정 보호를 검사한다.
`Use-UiHotfix.ps1 -Action Apply|Restore|Status -CandidateDir <후보> [-GameDir <게임 폴더>]`는
텍스트 파일 2개만 적용하며 백업은 후보 폴더의 `backup`에 둔다.
이전 test1 파일 4개는 상태 확인과 원복만 허용한다.
진단용 manifest의 `REPLAY_TIME_DIAGNOSTIC`은 루트/GUI의 `hud_leaderboard2_1_6.bgui` 두 복사본만,
`LAUNCHER_TEST`는 일반/VR 한국어 런처 두 파일만,
`MENU_FOOTER_TEST`는 `gui/menu_mainmenu_1_6.bgui`와 `gui/menu_mainmenuams2.bgui`의 상태 확인·원복만 허용한다.
다른 경로 조합은 거부한다.
Apply/Restore는 게임과 한국어 런처를 종료한 상태에서 실행한다.

테스트 중에는 기존 0.7 인스톨러의 상태 검사가 변경된 파일을 감지한다.
정규 설치 기록을 바꾸지 않으므로 테스트가 끝나면 이 도구의 Restore로 0.7을 먼저 복원한다.
스크립트는 `powershell -NoProfile -ExecutionPolicy Bypass -File ...`로 실행할 수 있다.
