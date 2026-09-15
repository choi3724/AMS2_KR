# Open Beta 0.85 validation

Fix: skip CM repair when no bootfile ownership is present, and accept intact files
from the recorded prior Korean installation before requiring a CM overlay recipe.
An actual unrecognized modification still stops repair without overwriting files.

Evidence root: E:\AMS2_Korean_Work\build\release085.
- Package preservation gate PASS: both manifests, existing localization assets and
  actual shipped installer/normal/VR menu reapplication.
- CM version guard: 5 checks PASS. The 0.84 control reproduces the intact old-record
  error; 0.85 accepts it. Both accept missing CM state; unknown edits remain blocked.
- Updater version ordering, release validation, extraction boundaries, cancellation,
  installer protocol and normal/VR launch arguments PASS.

The current report's remote-PC cause is not confirmed without its diagnostic ZIP.
CM is optional. First install/removal guidance from 0.84 remains in effect for CM users.
No real-PC installation is performed for this release. VR visuals are untested.
Legacy TEXT index tests use an explicit fixture; production retains official SHA1.

Final automated validation: 38 both-build lifecycle checks, 11 CM repair checks,
5 CM version-guard checks and 12 historical regression rejection checks PASS.
Lifecycle evidence: `build/qa085/17aaec05/result.json`.
