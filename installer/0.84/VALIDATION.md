# Open Beta 0.84 validation

## Changes

Reviewed CM generated bootfiles regain Korean translations/font routes before
normal/VR launch and installed-patch upgrade. Unknown shared edits are rejected.
CM-owned files are not removed by the uninstaller: disable CM before removal.
This is not a generic merge engine or a replacement for CM backup management.

## Evidence

- Ordinary game launch candidate confirmed working by the user on this PC.
- 0.84 package regression gate PASS: unchanged translation/font/menu/ERS assets,
  both manifests, actual shipped installer and normal/VR menu repair.
- Historical regression rejection suite: 12 checks PASS.
- Compiled 0.84 CM launch repair: 11 isolated checks PASS, including no-write
  repeat runs, regeneration, unknown edits, rollback and interrupted recovery.
- CM-active 0.83.3 to 0.84 upgrade PASS; uninstall refusal preserves game files;
  simulated CM disable then Korean removal RESTORED_EXACT.
- Updater version ordering, extraction, cancellation, installer protocol and
  normal/VR launch arguments PASS.

External evidence root: E:\AMS2_Korean_Work\build\release084.
Both-build lifecycle suite: 38 checks PASS (`build/qa084/f30022f7/result.json`), including 0.83.3 upgrades, legacy 0.7 and interrupted game updates.

## Boundaries

Physical VR and other PCs are untested. CM-disable tests simulate captured .orig
restoration rather than driving the CM app. Arbitrary other-mod edits are unsupported.
Legacy build 24132163 index content is unavailable; its isolated tests explicitly use
an index fixture while production retains the official size/SHA1 check.
