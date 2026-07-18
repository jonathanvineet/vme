# Full-document debugging report — why bar length & weight don't tally

Generated 2026-07-19 from a complete re-extraction of **all 11 DWG files**
(`python3 -m rebar3d.inventory`, full machine output in `out/FULL_INVENTORY.txt`).
Every entity in every file is now censused and categorized — nothing is skipped:
modelspace geometry by layer/type, every block INSERT, every text string,
and every paper-space table (all sheets carry schedules in **paper space**,
not modelspace).

## 1. What "everything" contains (categorized inventory)

| File | Modelspace entities | Paper-space cells | Content |
|---|---|---|---|
| PW-GF-02(R) | 9,634 | 84 | rebar (S-RBAR 596 m of rails), Summary Schedule |
| PW-GF-09(R) | 11,983 | 75 | rebar, Summary Schedule |
| SS-GF-01(R) | 7,429 | 73 | rebar, Summary Schedule |
| PW-GF-45(R) | 3,962 | 93 | rebar, Summary Schedule (no PDF exists — DWG paper space is the only source) |
| PW-GF-02(M1/M2) | 1,592 / 1,958 | 49 / 95 | mould: dims + **Projecting/Dowel/Insert/Weight schedules** |
| PW-GF-09(M1/M2) | 1,230 / 1,460 | 39 / 81 | mould schedules |
| PW-GF-29(M1/M2) | 706 / 537 | 39 / 99 | mould schedules (no R sheet on disk → no rebar model possible) |
| SS-GF-01(M) | 1,962 | 77 | mould schedules (N6=64×T8, N7=25×T16, Weight 1.93 m³/4,813.91 kg) |

Categories captured per file: geometry layers (S-RBAR bars, A-WALL outline/sleeves,
S-BEAM corbels/embeds, A-GENM anchors/loops, dimension/annotation layers), block
INSERTs by name (corbels, RR spread anchors, wire-loop boxes, channels), all text
(count callouts "N -Td", pitch callouts "Td @p", tie/U-bar/hook callouts, insert
marks Nn, dimensions), and paper-space tables (Summary / Projecting / Dowel /
Insert / Revision / Weight schedules + title block).

## 2. The single biggest reason "it doesn't tally": the official documents
disagree with each other, and they don't all cover the same steel

1. **BBS PDF ≠ R-sheet Summary Schedule** (both office-issued):
   - PW-GF-02: BBS total **318.96 kg** vs Summary **369.24 kg** (50 kg apart!)
   - PW-GF-09: BBS **390.93 kg** vs Summary **373.57 kg** (17 kg the *other* way)
   - PW-GF-09's BBS row 19 uses **T15** — a typo for T16 (unit wt printed 1.389 = 15²/162).
2. **Mould-sheet steel is separate scope.** Projecting bars (N6) and dowel bars
   (N7) live only in the M-sheet schedules — the R-sheet itself says "DOWEL BAR,
   PROJECTING BAR, U-BAR REFER INDIVIDUAL MOULD DRAWING". Proven arithmetically
   on SS-GF-01: N7's 25×T16 cannot fit inside the Summary's T16 total.
   True whole-panel steel = R Summary + M-sheet items:
   - PW-GF-02: + N6 19×T8, N7 13×T16 (M2)
   - SS-GF-01: + N6 64×T8 (420 mm drawn), N7 25×T16 (~740 mm) — drawn geometry count-verified exact
3. **The disk DWGs are an older revision than the printed PDFs** (PW-GF-02's DWG
   carries '2 -T16 CRACK BAR'×4; the print + BBS carry 8 more). PW-GF-02(M2)'s
   revision table shows Rev 2 "REVISED AS PER CLOUDED".

So a reconstruction can never tally against "the schedule" until *which*
schedule is chosen. Everything below reconciles against the R Summary Schedule
(per-diameter) **and** the itemized BBS (row-by-row) where it exists.

## 3. Current reconstruction vs official (fresh run, all fixes)

| Panel | recon length | official length | recon weight | official weight | wt % |
|---|---|---|---|---|---|
| PW-GF-02 | 477 m | 514 m | 332.2 kg | 369.2 kg | **90%** |
| PW-GF-09 | 495 m | 583 m | 309.7 kg | 373.6 kg | **83%** |
| SS-GF-01 | 341 m | 404 m | 261.1 kg | 321.0 kg | **81%** |
| PW-GF-45 | 267 m | 292 m | 140.7 kg | 166.4 kg | **85%** |

## 4. Row-by-row reconciliation (the actual debugging)

`rebar3d/inventory.py` now matches every reconstructed bar against every
itemized BBS row (same diameter, orientation-compatible, best length fit;
a folded U-loop books as 2 straight bars). Full tables in
`out/FULL_INVENTORY.txt`. Named gaps, largest first:

### PW-GF-09 (−63.9 kg vs Summary)
| BBS row | What | Matched | Missing | Root cause |
|---|---|---|---|---|
| 11 | 174× T8 closed tie 0.632 m | 103/174 | ~20 kg | ties drawn as sub-6 mm dash fragments; synthesis recovers 119 loops (38 land off-length and match no row) and 6× "T8 Hook @100 mm" callouts are a **still-unhandled family** |
| 9 | 20× T8 2.87 m "Horizontal" | 0/20 | 22.7 kg | **no matching geometry found anywhere** in the DWG (length = panel height but booked Horizontal); location unidentified |
| 10 | 120× T8 hairpin 0.868 m | 79/120 | ~13 kg | hairpins at rows the U-bar fold/synthesis still misses |
| 15 | 24× T10 5-segment 1.39 m | 0/24 | 20.6 kg | steel IS present (42 unmatched T10 v-mesh fragments = 23.9 m of the 33.4 m) but the 5-segment **shape is never assembled** from its fragments |
| 12 | 26× T12 vertical 2.87 m | 18/26 | ~20 kg | the "6 -T12" boundary-column detail sits in a zoomed top-connection view with bent/hooked ends — pair_lines wasn't built for detail-view arcs |
| 6 | 8× T16 full-width 3.94 m | 4/8 | ~25 kg | 4 full-width lines undetected in elevation |
| 16 | 2× T12 3.58 m | 0/2 | 6.4 kg | not found; likely same detail-view mechanism as row 12 |
| 19 | 2× "T15" 2.70 m | 2/2 ✓ | — | office typo for T16 |

### PW-GF-02 (−37.1 kg vs Summary)
| BBS row | What | Matched | Missing | Root cause |
|---|---|---|---|---|
| 13 | 160× T8 hairpin 0.868 m | 82/160 | ~27 kg | same hairpin undercount as PW-09 row 10 ("T8 UBAR @125"×11 callouts = one per row; fold+synthesis get ~half) |
| 12 | 58× T8 0.63 m end-links | 35/58 | ~5 kg | end-links of the U-system, partially found |
| 5 | 2× T16 4.84 m | 1/2 | ~8 kg | one full-length edge bar missing |
| 11 | 1× T12 3.70 m | 0/1 | 3.3 kg | single bar, not found |
| — | T16 crack bars | 4 of 8 in DWG | ~10 kg | DWG revision only *contains* 4 callouts (print has 8) + 4 of the 8 have no diagonal geometry in the DWG at all |
| phantom | T25 +3.1 kg, T32 +3.0 kg | — | −6 kg (extra) | witness-line junk pairs that still slip the 2 mm snap gate |

### SS-GF-01 (−59.9 kg vs Summary; no itemized BBS doc exists)
| Diameter | Have/Want | Missing | Root cause |
|---|---|---|---|
| T20 | 62.2/85.9 kg | 23.8 kg | slab edge-beam bars; one bottom-edge line is a **rail-assignment ambiguity** (rails y=96/108/117 pair as T12 vs T20); "2 -T20"×11 callouts unexploited |
| T16 | 52.5/67.5 kg | 15.0 kg | ~9 m of mesh undetected in elevation |
| T8 | 65.5/79.5 kg | 14.0 kg | R-internal links (98 found); note N6 projecting bars are *excluded* by arithmetic proof |
| T12 | 28.7/34.4 kg | 5.7 kg | ≈ one 4.8 m line — possibly the same rails as the T20 ambiguity read the other way (fixing one may fix both; don't double-count) |

### PW-GF-45 (−25.7 kg vs Summary; no BBS doc, no PDF — DWG paper space is sole truth)
| Diameter | Have/Want | Missing | Root cause |
|---|---|---|---|
| T16 | 21.0/34.1 kg | 13.1 kg | "2 -T16 Corbel Main Bar"×4 callouts — corbel main bars, **no synthesis pass handles them** |
| T12 | 23.3/33.8 kg | 10.5 kg | "2 -T12 Perimeter Bar"×6 — perimeter (opening-edge) bars, unhandled |
| T8/T20 | 98% / 103% | ~2 kg | effectively closed |

## 5. Established root-cause taxonomy (every gap is one of these)

1. **Doc-vs-doc disagreement** (§2) — not an extraction bug at all.
2. **Geometry drawn too fragmented to pair** (ties as 0.6 mm dashes, T10 lost
   under denser T8 mesh) — fixed where a text callout allows synthesis
   (ties, hairpins, crack bars); remaining: "T8 Hook @100", corbel main bars,
   perimeter bars.
3. **Geometry drawn as single centerlines** (crack bars, some full-width lines)
   — double-line pairing structurally can't see them; needs the labelled-single
   path per family.
4. **Shape never assembled from present fragments** (PW-09 row 15: 72% of the
   steel length exists as fragments, 0% booked as the 5-segment shape).
5. **Detail-view bars** (bent/hooked column bars in zoomed connection views,
   PW-09 rows 12/16).
6. **Rail-assignment ambiguity** (SS-GF-01 T20/T12 sharing a rail).
7. **Phantoms** (PW-02 T25/T32, +6 kg) — junk pairs passing the snap gate.
8. **Genuinely absent from the DWG** (PW-09 row 9, 22.7 kg; 4 crack-bar
   callouts with no geometry) — the disk DWG revision simply doesn't draw them.

## 6. Ranked next levers (kg each, per §4)

1. PW-09 hairpin/tie completion incl. "T8 Hook @100" family (~29 kg) + PW-02 hairpins (~27 kg) — same mechanism.
2. SS-GF-01 T20 rail ambiguity + "2 -T20" callout synthesis (~24 kg, may also fix T12's 5.7 kg).
3. PW-09 row-15 shape assembly from present fragments (~20 kg) — steel already detected.
4. PW-45 corbel-main + perimeter-bar callout synthesis (~23 kg).
5. PW-09 detail-view T12 rows 12/16 (~26 kg) — hardest (arcs in zoomed views).
6. Phantom suppression PW-02 (−6 kg of fake steel).

Items the user's `DRAWINGS/missing.txt` lists map as: "complete the dotted
lines" = fragment merging (§5.2/5.4), "corbel missing" = PW-45 corbel main bars,
"bending in the corners" = detail-view bent bars (§5.5), "double layers" =
front/back z-face assignment (largely fixed by the radius-tolerance fix),
"corrgated pipes" = sleeves (detected: 10 on PW-09, listed as features, not bars).

## 7. Session continuation findings (2026-07-19, `rebar3d-weight-fix-continued` branch)

Two fixes shipped and screenshot-verified:
- **Phantom suppression, generalized**: any v-mesh/h-mesh/diagonal bar at a
  diameter the panel's own Summary Schedule never lists at all is dropped
  (`cli.py::drop_unscheduled_phantoms`), gated on schedule availability and
  skipping synthesized/cast-in bars. Confirmed root cause on PW-02's T25/T32:
  each phantom sits almost exactly at the midpoint between two real,
  correctly-paired bars of *different* diameters (T12/T8, T20/T8) — a
  cross-pairing between one rail of each real bar, not real steel. Net
  effect: PW-02's naive TOTAL % *drops* 94%→92% because the +6kg of fake
  steel had been accidentally offsetting a real T16/T10 shortfall — an
  honest number, not a regression.
- **Hairpin synthesis now intersects per-run y-intervals** (was column
  overall min/max) so a v-mesh column split by a side notch gets hairpins
  at its own internal free ends too, the same pattern `_synthesize_ties`
  already handles. Small gain (PW-09 T8 +1.4kg) — only 5/19 T8 columns on
  PW-09 actually have an internal split, so this lever is mostly tapped out
  there; may matter more on panels with more notches.

Investigated but **not fixed this session** — each needs more evidence
before a safe synthesis rule can be written (placement-guessing has burned
this project multiple times; see §5-6 history):
- **PW-02's T10 −15kg "gap" is a doc-disagreement, not a bug**: PW-02's BBS
  row 10 wants only 2×T10@3.7m = 4.57kg total; the reconstruction (5.49kg)
  already *exceeds* the BBS figure. The −15kg only shows up against the
  Summary Schedule (20.50kg), which is simply a different, larger number for
  this diameter on this panel — same class of doc-vs-doc conflict already
  documented for PW-09's T16 (§2). Don't chase this one via geometry.
- **"T8 Hook @100mm" callout family (PW-09, 6 instances)**: each sits within
  ~500mm of one of the 6 "T8 Ties @100mm" callouts already driving
  `_synthesize_ties` (paired up spatially, one Hook label per Tie label per
  column zone) — almost certainly a companion single-leg hook/cross-tie in
  the same boundary-column detail, at the same 100mm pitch, not a duplicate
  label for the same steel. Likely a real, distinct ~20kg of BBS row-11
  weight, but its shape/placement relative to the tie loop isn't confirmed
  yet — needs a raw-geometry trace at one of the 6 label positions before
  synthesizing it (same standard as every prior synthesis pass here).
- **SS-GF-01's T20/T12 "rail ambiguity" from an earlier audit no longer
  reproduces at the described y=96/108/117** — current geometry shows T20 and
  T12 top/bottom edge lines at *different* z-depths (T20 near one face,
  T12 near the other), which is not actually ambiguous; likely already
  fixed by an intervening commit. The real remaining SS-GF-01 T20 gap
  (~9.6m / 23.8kg, suspiciously close to 2 more full-width 5.075m lines)
  and its 11 "2 -T20" callouts mostly sit **outside the elevation view's
  own bbox** (only 1 of 11 fell inside; PW-45's corbel/perimeter callouts
  are the same — only 1 of 12 lands in the elevation) — meaning most of
  this evidence lives in section/detail views that need per-view coordinate
  handling `crosscheck.py` doesn't do yet. Next step is building that
  drawing-wide (not elevation-only) callout-to-geometry search before
  attempting synthesis, same conclusion for PW-45's corbel-main/perimeter
  bars (task 4) and PW-09's detail-view T12 (task 5).
