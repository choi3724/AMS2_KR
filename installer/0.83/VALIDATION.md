# Open Beta 0.83 validation

Baseline: v0.82 / `8421f83176b86a61c5c9bdfdd6a9f523992e0463`.
Target: Steam public build `25271800`, V1.6.9.95.3432.

## Change and integrity

The game update replaced four menus and two HUD archives. Translation files remained,
but the menus lost their Korean font routes. The repair processes all 42,727 font fields,
including named widgets, and preserves all 15,332 Text records and other menu bytes.
Seven reviewed menu-specific font choices retain their verified new object identities.
New Steam menu geometry is retained; old whole menus are never copied over a newer game.

HUDDISPLAY contains 330 layouts. Eight layouts / thirteen ERS routes are patched;
the other 322 layouts and all non-target archive bytes remain unchanged. The IGPHASEHUD
tool changes only the existing driver-name entry. The pinned runtime from 0.82 is retained.

Repair validates installed state, path boundaries, current Steam menu provenance, font maps,
and archive/translation-index hashes before writes. It journals assets, metadata and backups,
rolls back failures, and recovers interrupted transactions before retrying. Current game stock
becomes the removal baseline; the previous backup is retained in the transaction journal.
Unknown formats, fonts, archive versions or manual changes require a reviewed patch.
No game executable, DLL, physics or network behavior is patched.

## Verification on 2026-09-13

- External C# build passed. CS0649 warnings for serializer-populated fields are retained in logs.
- `Test-GameUpdateCompatibility.py`: 26 checks passed with real copied assets and inert game EXEs.
  Coverage includes repeated Steam overwrites, font-only future menu repair, unknown-file refusals
  without writes, unsafe paths, missing fonts, locked/read-only files, late failure rollback,
  process-interruption recovery, 0.81/0.82 upgrades, repeated fresh installs and new-stock removal.
- Report: `E:/AMS2_Korean_Work/build/qa083/32294e47/result.json`.
  Test CLI SHA-256: `B8B9348A57F94171023458B7E4C55581FDF40CC327F6498334EF351A980A31DD`.
- Launcher version/URL/digest/protocol checks, unsafe ZIP refusal, normal/VR arguments and
  Pretendard rendering/text-fit checks passed. Current/offline/slow startup decisions were
  5013/5009/5017 ms; an available update pauses for a choice. Tests do not launch the game.
- The final 0.83 package upgraded this PC successfully (`UPDATED_EXACT`). The normal launcher
  started AMS2AVX, and the user's screenshot confirms Korean main-menu text on V1.6.9.95.3432.
  Game executable and protected-file invariant hashes matched before/after installation.
- Rebuilding compatibility assets from preserved old/new originals reproduced the tested
  rules, both archive deltas and all six patched candidates byte-for-byte.

## Reproduction

Use `Build-GameUpdateCompatibility.py --help` with verified old/new originals stored outside
Git. The authoring tool also requires the pinned local 0.82 package, mounted new Steam depot
manifest, and the existing external BffEntryInspect build. It refuses existing output folders.
Then build with `Build-InstallerOutsideRepo.ps1 -Version 0.83 -CompatibilityDataRoot <output>/data`.
`Build-Release083.py` assembles the package from that output and the verified 0.82 payload.
Run `Test-GameUpdateCompatibility.py --help` for fixture inputs. Test-only fault injection is
compiled with `COMPATIBILITY_TEST`; it is absent from shipped binaries.

## Runtime limits

The screenshot verifies the main menu, not every vehicle/display or game mode. All ERS modes,
multiplayer replay-save wording, physical VR, and the complete published update download/install/
automatic relaunch path still need runtime confirmation. Old saved safety-car names and replay
timer clipping remain unresolved. Four missing glyphs and thirteen translation-token issues
from the prior audit are unchanged. The old full uninstaller is not part of this release.
