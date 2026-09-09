# Open Beta 0.82 validation

Baseline: `v0.81` / `8c88447ec704462d690d59a55fba86485fc34377`.

## Build and scope

- Build externally with `tools/repository/Build-InstallerOutsideRepo.ps1 -Version 0.82`, then `tools/repository/Build-Release082.py`.
- The builder pins the 0.81 ZIP and the runtime-reviewed ERS candidate. There are 465 direct files: six replacements and sixteen additions relative to 0.81.
- Eight BGUI layouts / thirteen ERS mode-name routes use four dedicated Pretendard fonts. Original Arial and numeric LCD fonts remain unchanged. The tested `kr081_ers_value_*` asset names are retained to preserve the exact runtime-verified bytes.
- `HUDDISPLAY.bff` is reconstructed from a 69,963-byte gzip-compressed XOR delta. Both the 23,701,335-byte stock archive and patched archive must match their pinned SHA-256 values before installation writes any game assets. Unknown game archive versions are refused.
- The reconstructed archive is byte-identical to the successful Gen1 test: `F8A840F569D256DB4E1A67D73C5B2BB9CC4927E18109178B67356479BDCE81E5`. The ERS builder verifies the other 319 BGUI layouts and every byte outside the eight target allocations / size and CRC fields remain unchanged.
- Both BFF files participate in the existing transaction, backup, validation, rollback and removal process. Exact ERS test files can be adopted using verified historical backups and pinned inverse transforms; unrelated existing files retain their own backups.
- The runtime-tested IGPHASEHUD patcher is retained byte-for-byte from 0.81 (`4179D08A1452D497D612B0B371BF9C8881AFFDBEAE2389A9A1D393F85FA6AAA5`). Its build output is not substituted into the package.
- Game executables, DLLs, physics, vehicle/track data, menus and replay time layouts are not changed by this release.

## Verification

- `tools/repository/Test-Release082.py`: install/repeated install/check/removal twice; 0.81 upgrade/removal; exact ERS test adoption/removal; unknown/missing archive and corrupt/truncated delta refusal; rollback after a locked final archive; manual font-change preservation.
- Fixture result: 101 original files restored exactly and 366 patch-created files removed. No game is executed by this test.
- Normal/update-choice/scaled VR launcher rendering and text-fit checks pass using embedded Pretendard. Version and creator text are checked.
- Current/offline/slow startup decisions remain approximately five seconds. New versions pause for a choice; immediate launch skips the countdown. These tests do not launch the game.
- The shipped 0.81 updater recognizes the 0.82 version and installer protocol.
- Installer, normal/VR launcher assemblies and application manifests use `0.82.0.0`. User-facing installer: `AMS2 한국어 패치 오픈베타 0.82.exe`. No separate emergency removal tool is packaged.
- Detailed test logs, final package metadata, source commit and SHA-256 values live outside Git under `build/0.82` and `releases/0.82`.

## Runtime limits

The user confirmed Formula Ultimate Hybrid Gen1's normal cockpit ERS `균형` label. Other modes, the mode-change notification and other vehicle layouts remain unverified in game. Multiplayer replay-save wording, headset VR startup and the complete automatic download/install/game-relaunch path still need real-environment confirmation. Replay time clipping remains unresolved. Scaled rendering is not a physical monitor DPI test.
