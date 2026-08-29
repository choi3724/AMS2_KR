# Replay player-list time clipping — state variance analysis

## 결론

화면 상태에 따라 clipping 경계가 이동한 것이 아니다. 리플레이가 진행되면서 마지막 숫자가 바뀌어 잘린 모양만 달라졌으며, 측정 가능한 우측 경계는 모든 캡처에서 화면 x=528로 고정됐다.

또한 v34~v40에서 수정한 `Pakfiles/IGPHASEHUD.bff` 내부 BGUI는 런타임 활성 소스가 아니었다. Procmon은 AMS2AVX가 게임 루트의 loose `hud_leaderboard2_1_6.bgui`를 `CreateFile + ReadFile SUCCESS`로 읽는 것을 증명한다. 루트 loose 파일이 BFF 내부 후보를 shadow했으므로 이전 후보의 x/alignment/font-route 변경은 화면에 도달하지 않았다.

## 캡처

- idle 연속 20장: `runtime-evidence/replay-time-v39-idle-series/frame-001.png` ~ `frame-020.png`
- idle contact sheet: `runtime-evidence/replay-time-v39-idle-contact-sheet.png`
- slow wheel input: `runtime-evidence/replay-time-v39-slow-scroll-panel.png`
- slow input 종료 후: `runtime-evidence/replay-time-v39-slow-post-stop-panel.png`
- fast wheel input: `runtime-evidence/replay-time-v39-fast-scroll-panel.png`
- fast input 종료 후: `runtime-evidence/replay-time-v39-fast-post-stop-panel.png`

현재 리플레이에는 표시 행이 6개뿐이어서 wheel 입력으로 목록 자체가 이동하지 않았다. 그러나 리플레이 시간값은 계속 바뀌었고, 네 상태의 2~6행 모두 마지막 밝은 픽셀 경계가 x=528로 동일했다. 따라서 상태별 다른 template/scissor/fractional drift 가설은 기각한다.

## 활성 객체

활성 loose BGUI의 replay time 계열은 `SplitApplink` 11개이며 공통 속성은 다음과 같다.

- x=76, y=0, width=70, height=25
- right alignment
- font=`gui\\kr13_font_hud_main.bfont`
- 객체 시작 offset: 7530, 16522, 25514, 34506, 43498, 52490, 61482, 70474, 79466, 88458, 97450

다른 14개의 같은 이름 객체는 좌표·크기·font class가 다르며 현재 화면의 시간 열과 일치하지 않는다.

## 기하학

- 내부 행 parent width: 293 logical px
- `SplitApplink` current x/width: 76/70
- right-anchor 해석: left=293-76=217, right=217+70=287
- 외부 visible row edge: 284
- control overrun: 3 logical px
- 현재 숫자 glyph의 우측 raster overhang: 2 logical px
- 총 의도 픽셀 범위 초과: 약 5 logical px (현재 화면 약 10 physical px)

이 값은 실제로 마지막 숫자가 x=528에서 잘리고 완전한 glyph가 약 x=538까지 필요해 보이는 화면 측정과 일치한다.

## 최소 수정안

폰트를 변경하지 않고 활성 loose BGUI의 11개 replay time 객체에서 x만 76→81로 변경한다.

- 새 left=293-81=212
- 새 control right=212+70=282
- glyph overhang 2를 포함한 visible right=284
- 이름 열 right=203과의 간격=9

width, alignment, font, 한글/영문/숫자 metrics는 유지한다. 실제 활성 loose 파일에 이 변경을 적용한 런타임 POC가 먼저 통과해야 한다.
