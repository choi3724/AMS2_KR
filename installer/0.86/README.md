# Open Beta 0.86

0.86은 게임 빌드 번호를 참고 정보로만 사용하고, 설치·재적용·실행 시 현재 파일 구조를 검사한다.

- 98개 수정 BGUI는 현재 파일에서 필요한 폰트·검증된 표시 변경만 다시 적용한다.
- `IGPHASEHUD.bff`와 `HUDDISPLAY.bff`는 현재 아카이브의 대상 항목만 교체한다.
- Content Manager 공유 파일도 같은 후보 생성·백업·롤백 트랜잭션에서 처리한다.
- 필수 한글 자산 실패는 전체 목록을 보고하고 쓰기 전에 중단한다.
- 부가 HUD 아카이브 실패는 기존 핵심 한글 상태가 유효할 때 경고 후 실행을 허용한다.

빌드:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/repository/Build-InstallerOutsideRepo.ps1 -Version 0.86 -WorkRoot <작업 경로> -CompatibilityDataRoot <작업 경로>\build\adaptive086-data
```
