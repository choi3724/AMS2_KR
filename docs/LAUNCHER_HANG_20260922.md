# Korean launcher remains running without starting AMS2

Current-PC investigation, 2026-09-22. Baseline v0.87 (8f23282).

## Evidence and cause

The launcher had no window and accumulated CPU time on its main thread.
Two CLR stack samples located it in ContentManagerOverlay.Patch, through
Enumerable.Skip/Take/SequenceEqual, called by GameUpdateCompatibility.Ensure
and GameLauncher.Start. Steam had not yet received a launch request.

CM had regenerated 13 managed menu and translation files. The fallback byte
search enumerated from the beginning of the array at every candidate offset
on .NET Framework, causing quadratic traversal. This was not a Steam launch
failure or a game build rejection.

## Change

Use direct indexed comparison at the reviewed offset and a linear KMP scan
for relocated blocks. Keep missing/ambiguous block rejection, reverse-byte
validation, current-file backups, and existing transactional repair.

Recognize an already-applied block at its reviewed offset before searching
for an original block: other languages in drivers.tdb can legitimately retain
the original block. Repeat application must leave those languages unchanged.

## Validation

- Build installer, desktop and VR launchers, and test CLI.
- Ten search cases: fixed and shifted offsets, applied data, other languages,
  duplicate and overlapping matches, absent/empty patterns, and an 8 MB
  repeated-prefix adversarial scan (about 0.1 seconds for the suite).
- Read actual current-PC CM files, create candidates in memory, apply twice:
  all 13 passed, under 0.4 seconds per file for both passes.
- Launcher protocol/argument/update-package tests passed.
- Existing asset/translation/menu regression suite passed for installer and
  both launchers. Initial regression invocations used incomplete fixture roots;
  final run used preserved original/candidate fixtures and reported no issues.
- Actual current-PC repair completed: 13 reapplied, zero skipped, PASS.
- Installed both corrected launchers through the installer transaction;
  restored desktop/Start Menu shortcuts using ShortcutManager.Apply.
- Started the installed normal launcher. It exited and AMS2AVX PID 24944
  opened the Automobilista 2 window, responding, with `-lang Korean
  -looseloadtext` in its command line. In-game rendering remains user-verified.

Evidence and local builds: `E:\AMS2_Korean_Work\build\launcher-hang-20260922`.
The user subsequently confirmed Korean menu rendering by screenshot and
requested a v0.88 commit/release. See RELEASE_0.88_VALIDATION.md for the release
checks. VR visual output remains unverified; process start alone is not proof.
