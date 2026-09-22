# 0.88 validation

Baseline: public v0.87, commit 8f23282. Existing unrelated 0.84/0.86,
next, and universal-uninstaller work was preserved.

Change: fix quadratic CM byte searches and recognize the already-applied
translation block before searching unchanged blocks in other languages.
Build-independent compatibility, ambiguity rejection, backups and rollback
remain in place. Desktop and VR launchers share the same implementation.

Verified before publication:

- Final installer, launchers and test CLI built from installer/0.88.
- Ten search tests including overlapping matches and 8 MB repeated prefixes.
- All 13 captured CM files produce repeatable candidates; maximum measured
  two-pass processing time was 268 ms.
- Prior translation/font/menu/HUD regression gate passed; installer and both
  launchers passed the compiled menu reapplication verifier.
- Current/offline/slow update lookup proceeds after about five seconds;
  newer versions wait for user selection; manual launch remains immediate.
- Installer update protocol, extraction boundaries and normal/VR arguments
  passed. The parent-process verifier now obtains the expected version from
  the tested installer assembly.
- The user supplied a screenshot confirming normal Korean menu rendering on
  game 1.6.9.96.3436 after the equivalent local 0.87 diagnostic fix. This is
  separate from final 0.88 package tests; VR gameplay was not visually tested.
- Official 0.87 ZIP was verified against GitHub's SHA-256 and its payloads;
  its ownership entries were added through the existing common catalog model.

Final build: `E:\AMS2_Korean_Work\build\release088-final\build\0.88\installer`.
Package: `E:\AMS2_Korean_Work\build\release088-final\package`.
Evidence: `E:\AMS2_Korean_Work\build\release088`.

## Completed lifecycle validation

Thirteen representative lifecycle scenarios passed installation, reinstall,
launch-policy validation and uninstall: original-menu and six-column legacy
records, font-generation changes, skipped releases, ERS transition, 0.84,
0.85, 0.86, multiple histories, absent/broken records, and 0.87 to 0.88.
The final run also passed 14 retirement, ownership-conflict, rollback,
interruption, CM-preservation and desktop/VR parent-process checks.
Total: 66 lifecycle checks across the retained runs.

Evidence: lifecycle/*.log (six completed scenarios), lifecycle-rest/*.log
(four completed scenarios), lifecycle-last/result.json (26 checks), and
combined-result.json. Disk exhaustion interrupted one staging attempt;
completed temporary fixtures were removed with path containment checks.
A later running-game guard correctly stopped a test after the user restarted
AMS2. Remaining cases were resumed after game exit; neither interruption was
counted as a passing check. Production game files were not changed by this suite.
