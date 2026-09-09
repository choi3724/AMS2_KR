# 런처 업데이트 — Open Beta 0.81

## 동작

일반/VR 런처는 GitHub의 최신 정식 릴리즈를 확인하며 약 5초 동안 창을 표시한다. 기존 설치 프로그램의 레이스 이미지와 한글화 도구의 원본과 동일한 `Pretendard-Medium.otf`를 EXE에 내장했다. 검정·빨강 디자인에 `한글 패치 제작자 : ENGIceBlasT`, 패치 버전과 실행 모드를 표시한다.

런처의 라벨과 버튼은 PrivateFontCollection의 메모리 폰트 및 GDI+ 렌더링을 사용한다. 폰트 버퍼는 창이 사용하는 동안 고정하고 컨트롤·Font·컬렉션을 해제한 다음 반환한다. Windows에 폰트를 설치하지 않는다. [Microsoft 메모리 폰트 렌더링 안내](https://learn.microsoft.com/en-us/dotnet/api/system.drawing.text.privatefontcollection.addmemoryfont?view=netframework-4.8.1).

하단 제작자·버전·실행 모드 정보는 12pt 굵은 글씨다. 모든 런처 라벨과 버튼에 `TextRenderingHint.AntiAlias`를 지정해 색 번짐 없이 가장자리를 부드럽게 그린다. `AntiAliasGridFit`은 이 폰트의 10pt 안내·버튼에서 중간색 없이 그려지는 것을 확인하여 사용하지 않았다. [Microsoft 텍스트 렌더링 설정](https://learn.microsoft.com/en-us/dotnet/api/system.drawing.text.textrenderinghint?view=netframework-4.8.1).

`5초 후에 게임이 시작됩니다`부터 1초까지 카운트다운하며 최신 버전이면 자동 실행한다. 조회 실패/오프라인 또는 5초 이내에 응답이 없을 때도 현재 게임을 실행한다. 실제 조회가 일찍 끝나면 상태 문구를 갱신하고 남은 카운트다운을 유지한다. `지금 실행`을 누르면 대기 시간을 건너뛴다. 창을 닫으면 자동 실행을 취소한다.

새 버전이 있으면 카운트다운을 멈추고 `현재 버전으로 실행`과 `업데이트 후 실행`을 선택하도록 기다린다. 자동 실행은 하지 않는다.

업데이트를 선택하면 공식 ZIP의 크기·SHA-256을 확인하고 임시 폴더로 압축을 푼다. 설치 프로그램의 버전과 자동 업데이트 지원 표시를 확인한 뒤 설치 프로그램으로 넘기고 런처를 종료한다. 설치 프로그램은 기존 런처 종료를 기다린 후 기존 BetaEngine 설치·백업·롤백을 사용한다. 설치 후 `INSTALLED_EXACT` 검증을 통과해야 Steam으로 게임을 실행한다. 설치 단계는 필요한 Windows 권한 승인을 요청한다.

실행은 일반/VR 런처와 설치 프로그램 모두 `GameLauncher`를 통해 Steam `-applaunch 1066890`에 기존 한국어 옵션을 전달한다. 게임 EXE/DLL이나 Steam 설정 파일은 바꾸지 않는다.

## 확인 결과

- 전체 외부 빌드 통과.
- `0.7`, `0.7.0.0`, `Closed Beta 0.6.87`, `v0.7.1` 비교 및 다운그레이드 거부 통과.
- 정식 릴리즈·공식 다운로드 주소·해시·크기 검사 통과.
- 경로 이탈, 절대 경로, Windows 대체 데이터 스트림, 대소문자 중복 경로, 취소된 압축 해제 거부 통과.
- 실제 GitHub의 v0.7 메타데이터 및 58,492,128바이트 ZIP 다운로드·SHA-256·압축 해제 검사 통과. 구형 0.7 설치 파일의 자동 업데이트 실행은 규약 미지원으로 차단됨. 다운로드한 설치 파일은 실행하지 않음.
- 가상 새 버전의 업데이트 선택창 렌더링 및 버튼 문구 폭 확인.
- 테스트용 런처 적용·반복 적용·원복·수동 변경 보호 검사 통과.
- Steam 직접 실행은 사용자 무클릭 상태에서 게임 실행 보고 및 게임 프로세스 시작/정상 종료 로그를 확인함.
- 2026-09-09 초기 업데이트 런처(카운트다운 추가 전)를 평소 한글판 바로가기로 실행한 결과, 사용자가 추가 확인창 없이 한글 게임 시작을 확인함.
- 카운트다운 창의 최신/오프라인/응답 지연 자동 실행 결정을 각각 5,012/5,006/5,013ms에 확인함. 이 검사는 게임을 실제 실행하지 않음.
- 새 버전 발견 시 5초 이후에도 선택 대기, `지금 실행` 시 대기 건너뛰기 확인.
- 카운트다운·업데이트 선택창 및 150% 크기로 확대한 VR 창을 렌더링하고 표시와 문구 폭 확인. 실제 150% DPI 모니터에서의 검증은 별도다.
- 디자인·카운트다운을 추가한 일반/VR 런처를 백업 후 게임 폴더에 적용함. 이 후보의 실제 게임 진입은 사용자 확인 대기.
- Pretendard와 제작자 문구를 변경한 후속 후보도 일반/VR 두 EXE에 적용함. 실제 폰트 패밀리 `Pretendard Medium`, 정확한 문구, 일반·업데이트·VR 배치 및 카운트다운(최신 5010ms/오프라인 5011ms/조회 지연 5007ms) 검사를 통과함.
- 바탕화면 및 시작 메뉴의 `오모빌2 한글판 VR모드.lnk`가 수정한 게임 폴더의 `AMS2 Korean VR Launcher.exe`를 가리킴을 확인함. 실제 VR 헤드셋 진입은 미검증이다.
- 하단 크기·굵기와 가장자리 보정 후보(countdown3)의 일반·업데이트 선택·150% 크기 VR 렌더링 및 문구 폭 검사를 통과함. 안내·카운트다운·버튼·제작자 영역의 픽셀에서도 회색조 중간색을 확인함. 적용·원복 검사를 거쳐 일반·VR 두 런처에 적용하고 설치 파일 해시 일치를 확인했다. 실제 사용자 화면의 최종 가독성은 확인 대기다.

VR 실기 실행, 새 릴리즈를 설치하고 게임을 자동 재실행하는 전체 경로는 추가 검증이 필요하다. 개별 동작 검사를 실제 PC에서의 전체 경로 검증 완료로 표기하지 않는다.

## 배포 계약

- 다음 버전의 PackageManifest 버전/PackageId, AssemblyVersion/FileVersion, GitHub tag와 ZIP 이름을 일치시킨다. 오픈베타 ZIP의 GitHub 정규화 이름 `AMS2.<버전>.zip`과 기존 `AMS2.CB.<버전>.zip`을 인식한다.
- 새 설치 프로그램에는 `AssemblyDescription`의 `AMS2 Korean Patch Launcher Update Protocol 1` 표시를 유지한다. 이는 Windows 버전 정보의 `Comments`에 기록된다.
- Open Beta 0.81부터 사용자 실행 파일명은 `AMS2 한국어 패치 오픈베타 0.81.exe`다. 기존 CB 0.8 런처는 새 파일명을 인식하지 못하므로 이번 전환은 ZIP을 내려받아 수동 설치한다. 0.81 업데이터는 기존 CB와 새 오픈베타 이름을 모두 인식한다.
- 설치 프로그램은 ZIP 내 `manifest/direct-files.tsv`와 같은 폴더에 둔다. `AMS2 한국어 패치 오픈베타 <버전>.exe`와 기존 CB 이름 및 내부 빌드용 OB 이름을 인식한다.
- payload에는 새 일반/VR 런처와 승인된 번역만 넣고 direct-files.tsv 및 모든 배포 해시를 재생성한다. 개발용 테스트 EXE와 타이머 진단본은 배포하지 않는다.
- 로컬 시험 적용분은 원복한 후 정식 업데이트를 검사한다. 시험 파일을 기존 설치 기록에 몰래 편입하지 않는다.

## 재현 검사

`Build-InstallerOutsideRepo.ps1 -Version 0.81`은 `AMS2 Launcher Update Test.exe`도 외부 빌드 폴더에 만든다.

```powershell
& "$output\AMS2 Launcher Update Test.exe" $newTestDirectory "$output\AMS2-Korean-Patch-OB-0.81.exe"
```

마지막에 `--live`를 붙이면 GitHub 메타데이터 조회, `--render`는 개발용 창 렌더링,
`--startup`은 실제 약 5초 대기 및 새 버전 선택 대기 등 런처 동작 검사,
`--download-legacy`는 v0.7 ZIP 다운로드 및 구형 설치 파일 거부 검사를 수행한다.
검사 출력 폴더는 매번 새 경로를 사용한다. 어떤 모드도 설치 프로그램이나 게임을 실행하지 않는다.

참고: [GitHub 최신 릴리즈 API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release), [GitHub 릴리즈 자산 SHA-256](https://github.blog/changelog/2025-06-03-releases-now-expose-digests-for-release-assets/).
