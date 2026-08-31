# AMS2-KR-084 완료 보고서

## 시작 기준점

- Repository: `choi3724/AMS2_KR`
- 기준 버전: `v0.6.83`
- 기준 커밋: `0e698bec506feb93e83db1a6ff7c9384d0d5c5fc`
- 게임: Steam public build `24132163`

## 변경 요약

0.6.83의 고정 `IGPHASEHUD.bff` 크기/SHA/오프셋 검사를 제거했다. 새 self-contained 도구는 BFF를 파싱해 `gui\hud_infoabovecar.bgui` 한 엔트리와 `ProfileName` 한 객체를 식별하고, 지원되는 기존 경로를 `GUI\kr13_driver_name_semibold.bfont`로 변경한다.

변경 시 대상 엔트리의 압축 데이터, 원본/압축 크기와 CRC만 갱신한다. 다른 엔트리의 payload와 metadata 변화는 허용하지 않는다. 전체 BFF 크기와 SHA-256은 호환성 gate가 아니라 진단 정보로만 기록한다.

## 구조 검증

| 입력 | 입력 SHA-256 | 결과 SHA-256 | 결과 |
|---|---|---|---|
| build 24132163 순정 | `F967D1A3...E7DA` | `A3D4C1C3...2B39` | PASS |
| 0.6.83 legacy route | `D1618BB1...C398` | `A4A1A63E...08FC` | PASS |
| 순정 + trailing 4,096 bytes | `B9A4534B...6B7F` | `1324E652...2BD8` | PASS |

세 변형 모두 대상 경로는 `GUI\kr13_driver_name_semibold.bfont`, 비대상 payload 변경 0, 비대상 metadata 변경 0이었다. 합성 변형은 전체 BFF 크기 9,601,358 bytes에서도 정상 처리되어 고정 크기/SHA gate가 없음을 증명했다.

## 실제 설치·복원 검증

1. 0.6.83 설치 상태에서 0.6.84 업데이트: `INSTALLED_EXACT`
2. legacy 입력의 동적 결과: `A4A1A63E...08FC`
3. 제거/영문 원본 복원: `RESTORED_EXACT`
4. 복원 BFF: 순정 `F967D1A3...E7DA`, Phoenix route
5. 순정 입력에서 재설치: `INSTALLED_EXACT`
6. 최종 BFF: `A3D4C1C3...2B39`, dedicated Pretendard route

## Runtime

- 순정 복원 상태: `AMS2AVX` 정상 응답, 약 7.5 GB working set, BugSplat/Application Error 없음
- 0.6.84 설치 상태: `AMS2AVX` 1분 이상 정상 응답, Steam overlay 시작, 약 7.5 GB working set, BugSplat/Application Error 없음
- Beta 0.5에서 발생했던 REIZA 이후 즉시 크래시 회귀 없음

## 안전 계약

다음 조건에서는 설치를 fail-closed 한다.

- BFF 파싱 실패
- 대상 엔트리/`ProfileName`/지원 경로가 없거나 둘 이상
- 예상하지 않은 기존 글꼴 경로
- 새 압축 payload가 대상 allocation을 초과
- 재파싱/재추출/CRC 검증 실패
- 비대상 엔트리 payload 또는 metadata 변경

실패 시 live BFF를 교체하지 않는다. 설치 성공 후 제거 시 canonical 영문 원본 백업을 SHA-256까지 검증해 exact 복원한다.

## 제외 범위

- 번역 변경 없음
- BFONT/DDS 변경 없음
- Replay 시간 열 수정 없음
- physics/vehicle/track/network 변경 없음

## 릴리즈 패키지

- 파일: `AMS2 한국어 패치 CB 0.6.84.zip`
- 크기: `58,458,498 bytes`
- SHA-256: `FE1D58B96475E297CF5C9FA79B2DC13BCBCEB9FDDF2B90614E8A28B1BBCA7974`
- 최상위 폴더: `AMS2 한국어 패치 CB 0.6.84` 1개
- 내부 SHA-256 검증: `483/483 PASS`
- JSON/UTF-8 검증: `PASS`
- 이전 버전 인스톨러: `0개`
- 고정 `IGPHASEHUD-entry288.bin`: `없음`

## 최종 판정

`RELEASE_READY_V0.6.84`
