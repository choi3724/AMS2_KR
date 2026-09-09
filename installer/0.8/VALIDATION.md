# Closed Beta 0.8 validation

Baseline: `v0.7` / `0bfdafa09d6556539c57d193633eaa4f7b55efad`.

- Assemble with `tools/repository/Build-Release08.py` after the external 0.8 build. The input 0.7 ZIP is pinned by SHA-256.
- Of 449 direct files, only desktop/VR launchers and `text/game.tdb`, `text/drivers.tdb` change. Five Korean values change; other values, keys and language hashes are preserved.
- Original 0.7 menus, replay layouts, and the runtime-tested BFF patcher are retained. Failed menu-footer experiments are excluded. The shipped patcher retains the exact hash pinned by `BetaCore`; a new compile is not substituted.
- Production build, desktop/update-choice/scaled VR rendering and text-fit checks pass.
- Latest/offline/slow startup decisions: 5016/5013/5015 ms. A newer version pauses for a choice; immediate launch skips the countdown.
- `tools/repository/Test-Release08.py` tests install/check/removal twice, then 0.7 to 0.8 upgrade/removal in a new fixture. It includes unknown preinstall files and a preexisting file in a patch-created path.
- Upgrade backup handling now uses a matching prior installation's verified original before payload adoption rules.
- Final package checks and hashes are recorded outside Git under `build/0.8` and `releases/0.8`.

Runtime limits: multiplayer replay-save dialog, headset VR startup, and full download/install/game-relaunch remain unverified. Replay time clipping is unresolved. The 150% render is a form scale test, not a physical monitor DPI test.

## Inherited 0.7 validation (historical)

Baseline: `v0.6.87` / `8c82ff0b87353a6bb9d10960e6df1af4d4ddf3b2`

## Fix

- `gui\hud_infoabovecar.bgui` remains the only modified `IGPHASEHUD.bff` entry.
- The entry is recompressed with the stock-compatible zlib wrapper at level 6 instead of raw DEFLATE.
- The patcher rejects output without the expected zlib header before writing a candidate.
- Entry packed/original sizes and CRC are updated; unused allocation bytes are zero-filled.

## Verification

- Production patcher build: PASS.
- Source-generated BFF equals runtime-tested Case O: `D263F6805A2748E599013FDF0B73D4CCE557C52DA14103BFF9701682075F8011`.
- Repatch idempotence: PASS, zero changed bytes.
- Non-target BFF payload and metadata changes: 0.
- Physical runtime: pit crew PASS; dedicated Korean driver-name font and all five DDS pages loaded.
- Fixture install/check/remove repeated twice: PASS.
- Restored fixture originals: 95/95 exact.
- Patch-created fixture files removed: 355/355.
- Existing-file preserve-and-overwrite unit contract: PASS.

## Not verified in this build

- Pit STOP board and green ground marker during a full drivable pit sequence.
- Replay entry and playback after the compression fix.
- Replay time-column clipping remains outside this release.
