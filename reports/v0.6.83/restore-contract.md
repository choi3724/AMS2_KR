# v0.6.83 영문 원본 복원 계약

1. `modified` 파일은 설치 전에 canonical stock backup을 만들고 원본 크기와 SHA-256을 기록한다.
2. `created` 파일은 원본이 없었음을 기록하며 제거 시 패치가 소유한 exact 파일만 삭제한다.
3. 설치 실패 시 immediate transaction backup으로 설치 직전 상태를 복구한다.
4. 정상 제거 시 canonical stock backup으로 영문 원본을 복구한다.
5. 제거 후 모든 `modified` 파일의 SHA-256 일치와 모든 `created` 파일의 부재를 검사한다.
6. 소유권 ledger에 없는 사용자 파일·바로가기는 삭제하지 않는다.
7. 백업 누락·손상, 수동 변경, 혼합 상태는 서로 다른 상태로 보고하며 성공으로 위장하지 않는다.
8. `RESTORED_EXACT`는 원본 복구와 사후 검증이 모두 성공했을 때만 반환한다.

최종 실기 검증 결과: 95개 원본 복원 일치, 355개 생성 파일 잔존 0, 소유 바로가기 잔존 0.

