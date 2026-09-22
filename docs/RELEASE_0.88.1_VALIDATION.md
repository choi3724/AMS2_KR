# 0.88.1 validation

Baseline: public v0.88, commit 31a6313. Existing unrelated work is preserved.

Only the launch-notification policy changes: successful same-build repair
does not require acknowledgement, and an unchanged unknown build is not called
new. First processing of an unknown build and optional-repair warnings remain
visible. Validation, file writes, backups and failure handling are unchanged.

- Installer, normal and VR launcher compilation passed (version 0.88.1.0).
- Sixteen notification combinations passed on each shipped executable (48).
- Existing translation/font/menu regression gate passed, including compiled
  installer and both launcher menu reapplication.
- Five-second current/offline/slow lookup, new-version pause, manual launch,
  archive extraction and normal/VR command-line tests passed.
- Official v0.88 ZIP and payload hashes verified before catalog inclusion.
- Full 0.88 lifecycle/fault suite is retained as prior evidence; this focused
  release tests the immediate 0.88 upgrade, reinstall, launch policy and removal.
  All four focused lifecycle checks passed on isolated copies.

Evidence and package: `E:\AMS2_Korean_Work\build\release0881`.
The equivalent local 0.88 fix was installed successfully. Visual gameplay with
the final 0.88.1 package and VR gameplay are not independently verified.
