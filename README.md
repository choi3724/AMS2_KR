# AMS2 Korean Patch

Source repository for the unofficial Automobilista 2 Korean patch and its authoring tools.

For the current local work handoff and pending changes, read [PROJECT_MEMORY.md](PROJECT_MEMORY.md).

## Current baseline

- Version: Open Beta 0.83
- Author: ENGIceBlasT
- Reference game build: Steam public build 25271800 / V1.6.9.95.3432
- After installation, launch through `AMS2 Korean Launcher.exe` or an installer-created shortcut.
- Normal and VR launchers check changed game files and repair compatible menu font routes with backups. Unknown archive, translation-index, or font changes stop launch for a compatibility review.
- To remove the patch, choose `제거 / 복구` in the installer. After a supported game update, removal restores the newer game originals.
- The historical [full uninstaller](installer/0.82/RECOVERY.md) targets build 24132163 only. It is not included in 0.83 and must not be used to downgrade the current game.
- See [0.83 validation and reproduction](installer/0.83/VALIDATION.md) for test evidence and remaining runtime checks.

## Repository boundary

This repository contains source, project configuration, canonical source assets, and documentation. Compiled output and distribution archives are not committed.

- Build: `E:\AMS2_Korean_Work\build\<version>`
- Release: `E:\AMS2_Korean_Work\releases\<version>`
- Logs: `E:\AMS2_Korean_Work\logs`
- ChatGPT handoff: `E:\AMS2_Korean_Work\handoff`

See [Repository Artifact Policy](docs/REPOSITORY_ARTIFACT_POLICY.md) for the full contract.

## External build

Run the following command from PowerShell. Output is written outside the Git repository.

```powershell
powershell -ExecutionPolicy Bypass -File tools/repository/Build-InstallerOutsideRepo.ps1 -Version 0.83 -CompatibilityDataRoot E:\AMS2_Korean_Work\build\game-update-20260913-v3\data
```

`tools/AMS2-Asset-Studio` contains BFONT/DDS generation, BGUI adjustment, TDB editing, and analysis tools.

## Notes

- This is an unofficial, unsigned patch.
- Original game files, user backups, and personal environment data are never stored here.
- Before committing, run `tools/repository/Check-CommitArtifacts.ps1`.
