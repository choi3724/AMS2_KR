# AMS2 한국어 패치 Closed Beta 0.6.85 보고서

## 시작 기준점

- 원격/로컬 HEAD: `627b6ac6f3a2308479e2bf89c43efaae20d5570f`
- 기준 릴리즈: `v0.6.84`
- 원격/로컬 ahead/behind: `0/0`

## 수정 범위

- 배너 아래 `패치 검증 / Steam 빌드 / 패치 버전` 상태 카드만 수정했다.
- 원본 `status-card-base.png`는 2800×176(15.909:1)이며 변경하지 않았다.
- 상태 카드 행 높이를 화면 폭과 DPI에서 계산해 68~84px 범위로 제한했다.
- 카드 내부 상태 제목·상세 문구·패치 버전의 세로 위치와 높이를 같은 비율로 조정했다.
- 패치 버전 값의 가로 위치도 카드 폭에 비례하도록 변경해 960px 창에서 아이콘과 겹치지 않게 했다.
- 게임 번역, BFONT/DDS, BGUI/BFF, TDB 및 게임 payload는 0.6.84와 동일하다.

## 화면 검증

- 기본 창 1200×860: PASS
- 최소 창 960×700: PASS
- 상태 카드 세로 늘어짐: 0
- `패치 검증 / Steam 빌드 / 패치 버전 0.6.85` 겹침: 0
- 체크박스·주요 버튼·로그 영역 누락: 0
- 증거: `installer-1200x860.png`, `installer-960x700.png`

## 패키지 검증

- SHA256SUMS: 483/483 PASS
- 이전 버전 이름의 EXE/CONFIG: 0
- release manifest JSON parse: PASS
- ZIP files: 484
- ZIP checksum entries: 483/483 PASS
- ZIP SHA-256: `C817654ADC85BB6CE2687C71949FD9D02F8A70B1552DBEB73F9E5AF37E41D348`
- 기존 0.6.84 설치 감지: `UPDATE_AVAILABLE`
- 0.6.85 업데이트: `INSTALLED_EXACT`
- 제거/영문 원본 복원: `RESTORED_EXACT`
- 복원 후 SHA 검증: PASS
- 재설치: `INSTALLED_EXACT`
- 최종 게임 상태: 0.6.85 설치 완료

## 배포 정책

- GitHub Release tag: `v0.6.85`
- Pre-release: false
- Latest: true
- release asset: 최신 ZIP 1개

## 판정

`PASS_RELEASE_READY`
