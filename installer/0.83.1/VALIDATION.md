# Open Beta 0.83.1 validation

Baseline: published v0.83, commit 37a0e63eab7cc05cd841977770f2e9647740c4c7.
Supported game builds: 24132163 and 25271800. Unknown future builds keep the existing guarded repair path.

## Behavior

The installer selects a per-build direct manifest and ERS archive pair before checking, installing,
launching or removing the patch. Assets common to both builds are stored once. Four alternate menus
are exact 0.82 release bytes, retaining its existing non-font fixes; they are used only for build 24132163.
Legacy menu reapplication requires the exact old stock hash. Current-build font-only repair is unchanged.
Both normal/VR launchers select the same embedded rules by the installed Steam build.

The previous game's TEXT index is pinned to the official depot 1066891 manifest 3757163003589186571:
53149 bytes, SHA1 E69F8BCC367FCE781C5F4F09CB5537D85F3C4A86. The latest index retains its reviewed SHA256.
A build number alone never bypasses file validation. Missing/modified indexes and unsupported builds are refused.
Messages distinguish a supported build with differing files from an unreviewed game build.

Install state, backup rebasing, crash recovery and removal use the existing shared transaction logic.
No game executable, DLL, physics or Steam launch configuration is patched. The pinned 0.82 runtime is retained.

## Verification

- External production build passed. Compiler CS0649 serializer-field warnings remain in its log.
- 32 lifecycle checks passed: both builds' fresh/repeated install, state check, launch guard and removal
  twice; 0.7 upgrade on the old game; manual menu/archive changes refused; Steam update followed by
  interrupted repair/recovery; newer-game removal restores its newer originals; incorrect old index
  and unknown build messages are checked without game-asset writes.
- Evidence: E:/AMS2_Korean_Work/build/qa0831/46a1144e/result.json.
- The old TEXT index bytes are not available locally. Legacy fixture checks substitute ONLY its
  size-matched index SHA1 in a separate test CLI resource. All other game assets and C# source are real.
  Production retains the official Steam fingerprint, and is separately tested to reject that fake index.
  These tests must not be reported as a real old-PC installation or gameplay check.
- Latest-build lifecycle checks run the production CLI against real copied assets, with inert game EXEs.
- Normal/VR arguments, version ordering, protocol, unsafe ZIP refusal and Pretendard render/text-fit
  checks passed. Current/offline/slow waits: 5008/5017/5013 ms; new-version pause and immediate launch passed.
- Four old menu payloads and ERS bytes match the frozen 0.82 ZIP; latest assets remain the 0.83 payload.

## Reproduction

1. Build-LegacyCompatibility.py --current <verified 0.83 compatibility root> --output <new external root>.
   Requires the pinned 0.82 ZIP/extracted package, official old depot manifest and preserved stock.zip.
2. Build-InstallerOutsideRepo.ps1 -Version 0.83.1 -WorkRoot <root> -CompatibilityDataRoot <root>/data.
3. Build-Release0831.py --compatibility <root> --output <new external package directory>.
4. Test-LegacyCompatibility.py --compatibility <root> --package <package directory>.

The fixture CLI and synthetic index are outside Git and are never distributed. Release artifacts remain external.
The old standalone full uninstaller is not included and still targets build 24132163 only.

## Runtime limits

The old user's PC must confirm actual installation and Korean output after release. VR hardware, all ERS modes,
multiplayer replay-save wording and the complete published update/download/install/relaunch path remain unverified.
Replay timer clipping and the prior audit's glyph/token issues are unchanged. See the external handoff for final
commit, ZIP digest, public metadata/download checks and any current-PC installation result.
