# Repository Artifact Policy

## Purpose

Git stores reproducible source and configuration. Compiled output, distribution packages, runtime evidence, and task logs live in external work-root folders.

## Tracked content

- C#, Python, and PowerShell source
- Project files and build scripts
- Canonical source assets required for reproduction
- Installer image sources and redistributable source fonts
- README, policy documents, and concise release notes
- Existing `DynamicBffPatcher/lib` DLLs required as source dependencies

## External-only content

- `bin`, `obj`, build, and publish output
- EXE, PDB, and self-contained runtime output
- Distribution ZIPs and extracted release directories
- Test fixtures and mock output
- Screenshots, traces, logs, and diagnostic dumps
- ChatGPT handoff staging and ZIPs
- Temporary files and Python caches

## Fixed output roots

| Artifact | Location |
|---|---|
| Build | `E:\AMS2_Korean_Work\build\<version>` |
| Release | `E:\AMS2_Korean_Work\releases\<version>` |
| Logs and diagnostics | `E:\AMS2_Korean_Work\logs\<task>` |
| Handoff | `E:\AMS2_Korean_Work\handoff` |

Build and release tools must fail when an output path resolves inside the Git repository.

## Release reproducibility metadata

Each external release should record:

- source commit SHA
- version
- UTC build time
- compiler and SDK version
- output SHA-256 values

Do not retain versioned source copies under `build/v*`. Git commits and tags provide source history.

## Fonts and assets

Track one canonical copy of each source font and installer image. Generated BFONT/DDS files, copied button assets, and release payloads belong in external build or release roots.

## End-of-task checks

1. Run `git status --short`.
2. Run `tools/repository/Check-CommitArtifacts.ps1`.
3. Build outside the repository.
4. Confirm that Git status does not gain build output.

Future Codex tasks must not leave build, release, handoff, or log artifacts in the Git working tree.
