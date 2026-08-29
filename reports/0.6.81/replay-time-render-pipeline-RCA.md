# Replay time render pipeline RCA (pre-diagnostic)

Status: `PRE_DIAGNOSTIC_COMPLETE_ACTIVE_OBJECT_UNPROVEN`

This document freezes the evidence available before any new runtime diagnostic or fine-grained fix. It deliberately does not claim that candidate group A, B, or C is active.

## Verified route

1. AMS2 produces a dynamic replay/session split-time value. The observed presentation grammar is compatible with `m:ss.fff`, with optional sign and longer minute values.
2. The BGUI binding name associated with all current candidates is `SplitApplink`. The exact executable formatter symbol and call site have not been recovered, so formatter ownership remains engine-side and unresolved.
3. Procmon recorded `CreateFile`/`ReadFile SUCCESS` for `E:\SteamLibrary\steamapps\common\Automobilista 2\hud_leaderboard2_1_6.bgui`, including a full 197,354-byte read. That root loose file shadows the `gui/hud_leaderboard2_1_6.bgui` entry inside `Pakfiles/IGPHASEHUD.bff` for this test state.
4. The loaded loose resource contains 25 objects named `SplitApplink`. They form three distinct geometry/font groups: A (11), B (4), and C (10).
5. Existing screenshots show a stable visible cut boundary at full-desktop x=528 while displayed numeric values change. This proves a fixed final visible boundary in the sampled state, but it does not prove which BGUI object or parent owns that boundary.

## Not yet proven

- Which of groups A, B, or C supplies the visible replay time column.
- Whether the final clip owner is the text rectangle, a parent row/list, a runtime scissor, or a renderer-side viewport.
- Whether the exact formatter can emit every requested probe string (`0:00.000`, `0:59.999`, `1:23.456`, `9:59.999`, `12:34.567`) in one stored replay.
- Whether current glyph overhang contributes after the real active object and clip owner are proven.

## Prior-candidate disposition

Candidates v34-v40 changed the BFF-contained copy and were shadowed by the root loose file. Their lack of visible effect is not evidence for or against any object group. Candidate v41 made a small root-loose coordinate change, but a micro-change cannot establish object identity and its result is therefore inconclusive.

## Required proof protocol

No new fix candidate may be produced before the following runtime-visible proof:

1. Reuse a pre-existing diagnostic that moves one candidate group by at least 100 logical pixels.
2. Capture the replay/session list and compare it with the exact baseline.
3. If there is no movement, restore the source file byte-exact and test the next pre-existing group diagnostic.
4. If movement does not identify a group, reuse the pre-existing all-`SplitApplink` unbind diagnostic to make the bound column disappear.
5. Record deployed SHA, restored SHA, screenshot, observed displacement/disappearance, and process state for every run.

Only after active-object identity and clip ownership are runtime-proven may a minimal layout correction be considered. BFONT/DDS changes, Hangul width changes, Latin-letter width changes, and nameplate changes remain frozen. Digit/punctuation metrics are a last resort only after a proven layout path fails.

