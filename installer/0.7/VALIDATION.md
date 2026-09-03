# Closed Beta 0.7 validation

Baseline: `v0.6.87` / `8c82ff0b87353a6bb9d10960e6df1af4d4ddf3b2`

## Fix

- `gui\hud_infoabovecar.bgui` remains the only modified `IGPHASEHUD.bff` entry.
- The entry is recompressed with the stock-compatible zlib wrapper at level 6 instead of raw DEFLATE.
- The patcher rejects output without the expected zlib header before writing a candidate.
- Entry packed/original sizes and CRC are updated; unused allocation bytes are zero-filled.

## Verification

- Production patcher build: PASS.
- Source-generated BFF equals runtime-tested Case O: `D263F6805A2748E599013FDF0B73D4CCE557C52DA14103BFF9701682075F8011`.
- Repatch idempotence: PASS, zero changed bytes.
- Non-target BFF payload and metadata changes: 0.
- Physical runtime: pit crew PASS; dedicated Korean driver-name font and all five DDS pages loaded.
- Fixture install/check/remove repeated twice: PASS.
- Restored fixture originals: 95/95 exact.
- Patch-created fixture files removed: 355/355.
- Existing-file preserve-and-overwrite unit contract: PASS.

## Not verified in this build

- Pit STOP board and green ground marker during a full drivable pit sequence.
- Replay entry and playback after the compression fix.
- Replay time-column clipping remains outside this release.
