# Open Beta 0.83.2 validation

Public release note: 번역이 제대로 표시되지 않는 문제 수정

## Scope

- Latest verified BOOTFLOW tables supply native keys, record hashes and non-Korean values.
- 18 added entries and 10 changed English entries are translated; existing Korean translations and patch-only keys remain.
- Halo help visibility and its existing Korean binding are preserved in main and in-game menus on both supported builds.
- Package assembly verifies candidate hashes against compatibility rules instead of silently retaining old files.
- Installer, desktop launcher and VR launcher display 0.83.2; update protocol remains 1.

## Reproduce

From repository root, with Python on PATH (or the Codex Python runtime):

```powershell
python -B tools/repository/Build-GameUpdateCompatibility.py --game "E:\SteamLibrary\steamapps\common\Automobilista 2" --previous-originals E:\AMS2_Korean_Work\build\compat-legacy-20260913-v3\original-24132163 --current-originals E:\AMS2_Korean_Work\build\game-update-20260913-v3\original --output <new-current-root>
python -B tools/repository/Build-LegacyCompatibility.py --current <new-current-root> --output <new-compat-root>
powershell -ExecutionPolicy Bypass -File tools/repository/Build-InstallerOutsideRepo.ps1 -Version 0.83.2 -WorkRoot <new-compat-root> -CompatibilityDataRoot <new-compat-root>\data
python -B tools/repository/Build-Release0831.py --version 0.83.2 --compatibility <new-compat-root> --output <new-package-root>
python -B tools/repository/Test-TranslationRefresh.py --stock <new-current-root>\stock-text\text --baseline "E:\AMS2_Korean_Work\releases\0.83.1\AMS2 한국어 패치 오픈베타 0.83.1" --package <new-package-root>
python -B tools/repository/Test-LegacyCompatibility.py --version 0.83.2 --compatibility <new-compat-root> --package <new-package-root>
```

## Validation evidence

- Package translation checks: 9 tables, both 465-file manifests, 39 menu fonts, halo help on both menus/builds, rejection guards PASS.
- Launcher protocol, extraction safety, version comparison and desktop/VR arguments PASS.
- Startup countdown: online 5009 ms, offline 5013 ms, slow lookup 5009 ms; update offer waits for user action.
- Lifecycle: 38 checks PASS, including 0.83.1 → 0.83.2 upgrade and exact restoration on both supported builds. Evidence: `E:\AMS2_Korean_Work\build\qa0832\aba9cd21\result.json`.
- Canonical images/fonts/icons and third-party build dependencies are reused from 0.83.1; copied generated assets are not added to Git.

- Current PC upgraded from 0.83.1: UPDATED_EXACT; all 465 direct files match. Game EXEs, BOOTFLOW and PHYSICSPERSISTENT hashes remain unchanged. Game was not launched. Evidence: external `build/live0832-after.json`.

## Limits

The old build's actual TEXT index is unavailable locally. Legacy fixture tests substitute only its fingerprint; production continues to require the official depot size/SHA1. Fixture success is not old-PC gameplay confirmation.
Actual qualifying/halo screens, physical VR and multiplayer replay save are not verified by these automated checks. The remote all-asterisk report remains undiagnosed. Existing unrelated glyph/token issues, replay time clipping and other historic help-reference differences remain outside this release.
