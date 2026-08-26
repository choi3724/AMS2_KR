# AMS2 한국어 패치 Closed Beta 0.6.4

## 변경 사항

- 주행 중 차량 위에 표시되는 상대 플레이어 이름을 현재 한국어 패치와 같은 Pretendard 계열로 통일했습니다.
- `hud_infoabovecar.bgui`의 `ProfileName`만 전용 `kr13_driver_name_semibold` 폰트로 연결했습니다.
- 상대 이름 전용 폰트는 Pretendard SemiBold 20px, 1,344글자, 5개 atlas로 구성했습니다.
- 다른 HUD 글자 크기, 아이콘 폰트, 차량 계기판 및 전용 디스플레이 폰트는 변경하지 않았습니다.
- 0.6.3의 번역, 폰트 폭 조정 및 UI 결과를 그대로 유지했습니다.

## 실행

설치 후 Steam의 기본 실행 버튼이 아니라 설치 과정에서 만든 `오모빌2 한글판` 또는 `오모빌2 한글판 VR모드` 바로가기를 사용하십시오.

## 검증

- 0.6.3에서 0.6.4 업데이트 설치: PASS
- Main Menu → Single Race → 실제 주행: PASS
- 차량 위 상대 이름 출력: 사용자 직접 캡처 확인 PASS
- `**`, 잘림, 배경 사각형: 없음
- physics, vehicles, tracks, Generated Bootfiles 변경: 없음

## 무결성

ZIP SHA-256은 `reports/0.6.4/final-validation.json`에 기록됩니다.
