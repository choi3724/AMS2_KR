# Closed Beta 0.6.87 validation

Baseline: `v0.6.86` / `e19e0cbfbe7fac0d956d1e3514918625c90572fe`

## Install contract

- Direct replacement files no longer require a known stock SHA.
- Any unknown existing direct file is backed up before overwrite and restored byte-for-byte on removal.
- A file absent before installation is removed on uninstall.
- Missing required modified files still block installation.
- `IGPHASEHUD.bff` retains structural inspection and the single-entry dynamic patch contract.
- Package payload size and SHA-256 validation remains mandatory.

## Verification

- Unit test: unknown `created` and `modified` files preserved — PASS.
- Manifest: 449 rows (94 modified, 355 created) — PASS.
- Unknown `text/drivers.tdb` install — `INSTALLED_EXACT`.
- Unknown `text/drivers.tdb` removal — exact preinstall SHA restored.
- Unknown modified BGUI install/removal — exact preinstall SHA restored.
- Dynamic `IGPHASEHUD.bff` patch and restore — PASS.
- Reinstall and final status — `INSTALLED_EXACT`.
- Release folder SHA verification: 484 files — PASS.
- ZIP extract and SHA verification: 484 files — PASS.
- Microsoft Defender folder and ZIP scans — no threats, exit code 0.

Release ZIP SHA-256:

`EDB2C59320D83AE9383ED9D455C1582F8F8AB23F82E576408C77B74F1A08C88B`
