# AMS2-KR-064 결과 보고서

## 최종 판정

`PASS — DRIVER_NAME_FONT_RUNTIME_CONFIRMED`

Closed Beta 0.6.3을 기준으로 주행 중 차량 위 상대 이름의 폰트만 전용 Pretendard SemiBold로 교체했습니다. 다른 HUD 및 차량 전용 폰트는 변경하지 않았습니다.

## 변경 내용

- 대상: `hud_infoabovecar.bgui`
- 객체: `ProfileName`
- 이전 경로: `gui\\kr13_phoenix_body_regular.bfont`
- 새 경로: `gui\\kr13_driver_name_semibold.bfont`
- 새 폰트: Pretendard 1.3.9 SemiBold, 20px
- 글리프: 1,344개
- atlas: 1,024×512, 5개
- BGUI 크기: 3,604바이트 유지
- 대상 외 BGUI 바이트 변경: 0

## 주요 SHA-256

- 수정 BGUI: `BC8CAE988E7FD47B4BC330139E0C1C150C5265E3FC76BC4B1B42BBB5014AE082`
- 전용 BFONT: `B8664D4ED2D9BBF66F37D407A53C6E13C1651A0A1A58D756CFE8C231371BFA9A`

## 패키지 차이

- 0.6.3에서 그대로 유지: 438개
- 변경: 4개
- 추가: 전용 BFONT/DDS 6개
- 제거: 0개
- 최종 direct payload: 448개

변경 4개는 일반/VR launcher 2개와 root/GUI `hud_infoabovecar.bgui` 2개입니다.

## 설치 및 런타임

- 0.6.3 감지: `UPDATE_AVAILABLE`
- 0.6.4 업데이트: `UPDATED_EXACT`
- 최종 상태: `INSTALLED_EXACT`
- Main Menu: PASS
- Single Race 설정: PASS
- 실제 세션 및 주행 HUD: PASS
- 차량 위 상대 이름: 사용자 직접 캡처로 PASS
- `**`, 잘림, 배경 사각형: 관찰되지 않음

## 불변 조건

- `PHYSICSPERSISTENT.bff` 변경 없음
- `PHYSICSPERSISTENT.bff-remove` 생성 없음
- vehicles/track physics 생성 0
- CRD/TRD/driveline 처리 0
- AMS2CM/dotnet/Generated Bootfiles 사용 없음

## 현재 상태

개발 PC에는 Closed Beta 0.6.4가 설치 완료 상태로 남아 있습니다.
