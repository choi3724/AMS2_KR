# AMS2 Project Memory

## Open Beta 0.85 — 2026-09-15

User authorized release and commit. Fix intact older installation records being
rejected by CM compatibility checks; CM absence returns without repair. Unknown
mod edits remain blocked. Source installer/0.85; evidence build/release085.
Actual report-PC cause remains unconfirmed without its ZIP. No real-PC install
is authorized in this release task.


## Open Beta 0.84 — release preparation 2026-09-15

User authorized commit/tag/push/release. Source installer/0.84 includes reviewed CM
bootfile overlays before normal/VR launch and installed-patch upgrade. Normal game
launch candidate confirmed by user; VR remains unconfirmed. Disable CM before
Korean uninstall; arbitrary shared mod edits remain unsupported. Build and test
evidence: E:\AMS2_Korean_Work\build\release084. Read docs/CONTENT_MANAGER_COMPATIBILITY.md.


## Regression prevention — 2026-09-14 (unreleased maintenance)

The user requested preparation against losing old fixes in later patches.
Read docs/REGRESSION_PREVENTION.md before future game-update/release work.
Build-Release0831.py now gates 0.83.3+ assembly on the reviewed baseline,
both manifests, independent help invariants and actual installer/desktop/VR menu repair.
The baseline is not automatically promoted from new candidates. Intentional asset
changes require exact before/after hashes, rationale and verification evidence in Git.
No new game patch/release is authorized by this maintenance request.

## Open Beta 0.83.3 — 2026-09-14

The user authorized 0.83.3 with the exact public note `누락된 부분의 번역 수정`.
The inline HUD beta explanation in menu_mainmenu_1_6.bgui is translated again
for both supported game builds; it is not a missing TDB entry. Shared launcher
repair preserves the literal replacement and rejects changed/duplicate originals.
Sources are in installer/0.83.3; the 0.83.2 source snapshot remains unchanged.
External compatibility/build root: build/hud-beta-help-legacy-20260914-v2.
Read installer/0.83.3/VALIDATION.md for checks and actual-game limits.

## Open Beta 0.83.2 — 2026-09-13

The user authorized a 0.83.2 release with the exact public note:
`번역이 제대로 표시되지 않는 문제 수정`.
Native BOOTFLOW translation tables now supply the key sets and non-Korean values;
18 missing keys and 10 changed English entries are reviewed, preserving prior Korean values.
Both main/in-game halo help routes and visibility are restored for both supported builds,
and the shared update repair keeps these corrections with record fingerprint checks.
Read `installer/0.83.2/VALIDATION.md` for final test evidence and remaining issues.
Source assets are built outside Git under `build/translation-halo-legacy-20260913-v1`.
The unrelated remote-PC all-asterisk report is unresolved because its diagnostic files were deleted.
Other historic help-reference differences are recorded in the external qualifying analysis;
do not blindly restore them because some reuse keys later corrected for replay messages.

## Open Beta 0.83.1 — 2026-09-13

The user requested accurate error messages, installation on the previous game build, and a 0.83.1 release.
The new installer/normal/VR launcher share profiles for builds `24132163` and `25271800`.
Four legacy menus are byte-identical to the reviewed 0.82 payload, preserving its non-font changes too.
Legacy ERS uses the old reviewed archive pair; current menus/archives remain the 0.83 assets.
Unknown builds and changed files have distinct messages; the compatibility guard is retained.

Read `installer/0.83.1/VALIDATION.md` and the external
`E:\AMS2_Korean_Work\handoff\AMS2_작업인계_0.83.1_2026-09-13.md` for final release/test identifiers.
Candidate root: `build/compat-legacy-20260913-v3` outside Git. Do not use v1/v2 intermediates.
The old TEXT index content is unavailable locally: production pins its official Steam depot size/SHA1;
old-build fixture tests explicitly substitute only that index fingerprint. Actual old-PC display remains a user check.
Do not describe fixture tests as a real old-game execution or overwrite the published 0.83 ZIP.

## Open Beta 0.83 — 2026-09-13

The user authorized repair, commit, and publication of 0.83, with progress updates.
0.83 supports Steam build `25271800` / V1.6.9.95.3432. The final package was installed on
this PC; the user supplied a screenshot confirming normal Korean main-menu text.
Normal/VR launchers now repair compatible updated menu font routes, preserve current game
originals for removal, and stop for unknown archive/translation/font changes. This is not
a guarantee that all future game updates work automatically.

The 26 installation/repair/recovery fixture checks passed, including interrupted repair,
manual-change protection, 0.81/0.82 upgrades, and restoration to new game originals.
See `installer/0.83/VALIDATION.md` and the external handoff
`E:\AMS2_Korean_Work\handoff\AMS2_작업인계_2026-09-13.md` for final release identifiers.
Build evidence and the tested candidate are in `build\game-update-20260913-v3` outside Git.
Do not use the rejected v1/v2 menu candidates, which missed named widgets.

Multiplayer replay-save wording, replay timer clipping, all ERS modes, physical VR, and the
complete automatic download/install/relaunch flow remain unverified or unresolved as noted
in validation. Four missing glyphs and 13 translation-token discrepancies remain unchanged.
The old full uninstaller is restricted to build 24132163; do not ship it for build 25271800.

## Initial game-update diagnosis — 2026-09-13 (historical)

The current local game is now V1.6.9.95.3432 / Steam build `25271800` (updated 2026-09-12 23:42:29 KST).
Open Beta 0.82 targets the previous build `24132163`. Four menu BGUI files and IGPHASEHUD/HUDDISPLAY
were replaced with verified new Steam originals. All four menus now have zero Korean font references;
461 of 465 direct patch files still match 0.82. This explains the reported menu `**` output.
Read `E:\AMS2_Korean_Work\analysis\update-20260913\진단결과.md` before the older handoff below.
The initial no-patch state was superseded by the 0.83 work above. Do not overwrite
new game menus with old menu files or bypass the old full uninstaller's build check.

## Previous work handoff — 2026-09-10 (historical)

Read `E:\AMS2_Korean_Work\handoff\AMS2_작업인계_2026-09-10.md` before resuming work.
The published baseline is Open Beta 0.82 (`8421f83176b86a61c5c9bdfdd6a9f523992e0463`).
Subsequent recovery/update changes are uncommitted and unreleased. Preserve the working tree.
The separate full uninstaller passed 16 fixture checks; its actual stock-font appearance check is pending.
Four missing Korean glyphs and 13 translation-token discrepancies remain unmodified.
Do not commit, tag, push, or publish a new release without a new user request.

This is a dated handoff pointer. Verify current files and remote release state when resuming.

## GitHub Release Korean text encoding rule

This rule is mandatory for every future AMS2 Korean patch release.

1. Do not place Korean release title or body literals directly in a BOM-less Windows PowerShell 5 `.ps1` file.
2. Keep the intended title and body in a UTF-8 Markdown file.
3. Read that file with strict, explicit UTF-8 decoding:
   - `New-Object Text.UTF8Encoding($false, $true)`
   - `[IO.File]::ReadAllBytes(...)`
4. Serialize the GitHub API payload to JSON, then send explicit UTF-8 bytes rather than a PowerShell string:
   - `(New-Object Text.UTF8Encoding($false)).GetBytes($json)`
5. After creating or updating a release, fetch it from GitHub and verify:
   - release title exact match
   - release body exact match with the UTF-8 Markdown source
   - replacement character count is zero
   - repository Markdown files are byte-exact with the local Git commit
6. A Release metadata correction must not replace or modify the tested ZIP asset.

Root cause recorded on 2026-08-26: Windows PowerShell 5 interpreted Korean literals in a BOM-less UTF-8 release script as ANSI. Git repository files and the ZIP were correct; only the GitHub Release title and body were corrupted.

## Release file naming rule

The user's Open Beta naming request from 0.81 onward supersedes the earlier CB naming rule.
Use this base filename for the main patch installer and ZIP, with the user-approved version:

`AMS2 한국어 패치 오픈베타 <버전>`

Examples:

- `AMS2 한국어 패치 오픈베타 0.82.exe`
- `AMS2 한국어 패치 오픈베타 0.82.zip`

This rule applies to user-facing release filenames. Do not rename internal package IDs or the normal/VR launcher executables unless separately instructed.
The existing GitHub asset is `AMS2.0.82.zip`; do not rename or replace it while preparing a future release.
Separate recovery tools keep their descriptive filenames, such as `AMS2 한국어 패치 완전 제거.exe`.
