# Next Step

다음 작업은 v0.6.8 일반 폰트를 다시 만들지 않고, 별도 전용 nameplate POC로 제한한다.

1. 순정 `IGPHASEHUD.bff`와 현재 전용 폰트를 Known-Good로 보존한다.
2. 전용 nameplate renderer 계약에 맞춘 작은 Pretendard 폰트만 별도 생성한다.
3. 실제 Single Race에서 영문, 한글, 숫자, human nickname을 비교한다.
4. 한 글자라도 깨지거나 clipping되면 순정 route로 즉시 복귀한다.

거리 formatter와 번역 데이터는 별도 작업으로 유지한다.
