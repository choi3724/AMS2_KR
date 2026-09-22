# Open Beta 0.88

0.88은 CM 파일 검사 지연으로 게임이 시작되지 않는 문제와 번역 중복 적용 판정을 수정했습니다.

구버전 설치 기록과 정식 배포 파일을 확인해 중간 버전 없이 최신 패치로 업데이트한다. 게임 빌드 번호를 참고 정보로만 사용하는 0.86 정책도 유지한다.

- 설치 기록의 버전·폴더명·파일 개수가 달라도 공통 형식으로 읽고 실제 파일과 대조한다.
- 일반·VR 런처를 포함한 패치 소유 파일은 검증된 이전 기록 또는 정식 배포 파일 해시로 인계한다.
- 후보 전체를 검증한 뒤 반영하며, 실패·중단 시 파일과 설치 기록을 작업 직전으로 복구한다.
- 원본 백업이 없어 순정 복원을 입증할 수 없으면 전체 업그레이드 직전 상태를 보존하고 안내한다. 이 경우 제거는 순정 복원이 아니라 업그레이드 직전 상태 복원이다.

- 98개 수정 BGUI는 현재 파일에서 필요한 폰트·검증된 표시 변경만 다시 적용한다.
- `IGPHASEHUD.bff`와 `HUDDISPLAY.bff`는 현재 아카이브의 대상 항목만 교체한다.
- Content Manager 공유 파일도 같은 후보 생성·백업·롤백 트랜잭션에서 처리한다.
- 필수 한글 자산 실패는 전체 목록을 보고하고 쓰기 전에 중단한다.
- 부가 HUD 아카이브 실패는 기존 핵심 한글 상태가 유효할 때 경고 후 실행을 허용한다.

빌드:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/repository/Build-InstallerOutsideRepo.ps1 -Version 0.88 -WorkRoot <작업 경로> -CompatibilityDataRoot <검증된 호환성 데이터> -VerifiedBffPatcher <정식 0.86의 변경 없는 BFF 적용기>
```

정식 배포 식별 목록 생성과 검증 범위는 `docs/RELEASE_0.88_VALIDATION.md`에 기록한다.
