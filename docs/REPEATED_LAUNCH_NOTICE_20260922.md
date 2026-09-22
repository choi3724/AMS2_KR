# Repeated successful CM repair notification

Current-PC 0.88 evidence: the active record is already build 25391793;
multiple game-updates transactions finish with `PASS build=25391793 files=13`.
Routine CM regeneration therefore produces real successful repairs on the
same build. `ShouldNotify` included every positive Reapplied count, while
Notice called any unknown build a new build even when BuildChanged was false.

Successful same-build repair no longer requests a modal acknowledgement.
First processing of an unknown build and skipped optional-item warnings still
notify. Required failures still throw through the unchanged validation path.
Notice only calls a build new when it actually changed. Transaction backups,
result.txt records and the repair policy are unchanged.

Validation: 16 notification combinations each on the compiled normal launcher,
VR launcher and installer (48 checks); existing asset/menu regression suite
passed. Output: `E:\AMS2_Korean_Work\build\notice088`.
This follow-up is released as 0.88.1; the published 0.88 release is not replaced.
