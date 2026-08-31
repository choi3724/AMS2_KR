# AMS2 Korean Patch

Source repository for the unofficial Automobilista 2 Korean patch and its authoring tools.

## Current baseline

- Version: Closed Beta 0.6.85
- Author: ENGIceBlasT
- Reference game build: Steam public build 24132163
- After installation, launch through `AMS2 Korean Launcher.exe` or an installer-created shortcut.

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
powershell -ExecutionPolicy Bypass -File tools/repository/Build-InstallerOutsideRepo.ps1 -Version 0.6.85
```

`tools/AMS2-Asset-Studio` contains BFONT/DDS generation, BGUI adjustment, TDB editing, and analysis tools.

## Notes

- This is an unofficial, unsigned patch.
- Original game files, user backups, and personal environment data are never stored here.
- Before committing, run `tools/repository/Check-CommitArtifacts.ps1`.
