# Open Beta 0.83.3 validation

Public release note: 누락된 부분의 번역 수정

## Scope

The new HUD beta explanation is a length-prefixed UTF-16 literal in
`gui/menu_mainmenu_1_6.bgui`, outside the translation tables. Its earlier Korean
translation was lost when the newer game menu was rebuilt from stock.
`hud_beta_help.py` restores the reviewed text on both supported builds, and the
shared installer/normal/VR `GameUpdateCompatibility` preserves it on reapplication.
Unknown or duplicate source literals stop repair. Other menu fields, existing halo
help, translations, fonts, ERS assets and the updater protocol remain intact.

Installer and both launchers display 0.83.3. Canonical images, fonts, icons and
build dependencies are reused from 0.83.1.

## Reproduce

Use Build-GameUpdateCompatibility.py and Build-LegacyCompatibility.py as in the
0.83.2 validation instructions, with fresh output directories. Build with
Build-InstallerOutsideRepo.ps1 -Version 0.83.3 and Build-Release0831.py --version 0.83.3.
Run Test-TranslationRefresh.py against the assembled package and
Test-LegacyCompatibility.py --version 0.83.3 for both build lifecycles and upgrades.
External compatibility/build root: E:/AMS2_Korean_Work/build/hud-beta-help-legacy-20260914-v2.

## Validation evidence

- Translation/package checks PASS: 9 tables, both 465-file manifests, 39 menu fonts, halo and HUD beta help in both builds.
- Installer/normal/VR runtime menu checks PASS: 24 byte-exact menu outputs plus changed/duplicate literal rejection.
- Lifecycle 38 checks PASS, including 0.83.2 upgrade/removal on both builds, legacy 0.7 upgrade, interrupted game update recovery and manual-change protection. Evidence: external `build/qa0833/18bca945/result.json`.
- Launcher version/extraction/protocol/desktop-VR arguments PASS. Countdown: online 5022 ms, offline 5016 ms, slow 5006 ms; update offer pauses for user action.
- Current PC: 0.83.2 to 0.83.3 UPDATED_EXACT, 465 direct files verified. Game EXEs, BOOTFLOW and PHYSICSPERSISTENT unchanged. Game not launched. Evidence: external `build/live0833-after.json`.

## Limits

Actual help-panel layout, physical VR and multiplayer gameplay require in-game
checks. The old build's unavailable TEXT index uses a declared fingerprint fixture;
production still requires its official size/SHA1. Automated results do not resolve
the unrelated remote-PC all-asterisk report.
