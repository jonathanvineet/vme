# Registration audit: does (M) share a coordinate frame with (R)?

**No code was written or modified.** Tests the hypothesis raised by the N7 trace — "SS-GF-01(M) and SS-GF-01(R) are drawn on the same template at the same coordinates" — against every (M)/(R) pair actually available, with exact measurements.

**Scope, stated honestly upfront**: the corpus holds **one project**, not five or six. Apollo contains three elements with an (M)/(R) pair each — `SS-GF-01`, `PW-GF-09` (with two mould sheets, M1+M2), `PW-GF-02` (also M1+M2) — giving **5 sheet-pairs, n=3 elements, all one consultant, one project**. This is a within-project replication test, not a cross-project one. Treat every conclusion below as scoped to that.

## Result, stated first: the hypothesis does not hold as "same coordinates." It holds, weakly, as "coincidentally close start point" — for one sheet type, not the other.

## Measurements

### SS-GF-01(M) vs SS-GF-01(R) — the pair the original trace was built on

Symbol-by-symbol offset (R minus M), same-labeled section markers:

| Symbol | M | R | Offset (Δx, Δy) | Distance |
|---|---|---|---|---|
| 1 | (62709.8, 25397.7) | (62852.2, 25793.6) | (+142.4, +395.9) | **420.7mm** |
| 2 | (67996.5, 24402.9) | (68019.8, 24459.9) | (+23.3, +57.0) | **61.6mm** |
| 3 | (65996.5, 24402.9) | (65929.8, 24424.6) | (−66.7, +21.7) | **70.1mm** |

**This is not a rigid transform.** A true shared-frame registration (even an imperfect one — pure translation, rotation, or scale) would produce a *consistent* offset vector or a offset that scales predictably with distance from a rotation center. These three offsets point in different directions with no shared magnitude or angle. The `A-FLOR` layer's bounding-box minimum corner matching to the millimeter (63183.04258574973, reported identically in both files) — the fact the previous trace leaned on — is very likely a **shared block-insertion origin** for a repeated floor-outline block, not evidence the whole drawing is registered. One exactly-matching number is not the same claim as "the sheets share a world."

**Correction to `docs/research/apollo_n7_trace.md`**: that document's §3 states "SS-GF-01(M) and SS-GF-01(R) are drawn on the same template at the same coordinates" and describes the T8@200/N7 co-location as "11mm from the N7 row band" as if that were high-precision confirmation. Both statements overclaimed. The 11mm figure is real, but this audit shows same-labeled reference points on this exact sheet pair disagree by up to 421mm — so an 11mm match is *consistent with* a real correspondence, but is not distinguishable from being within the same ~400mm noise band by chance, given how few candidate labels exist near that band. **VQ-002's confidence is revised down accordingly** (see below). This is left as a correction note, not a silent edit — matching how Phase 9.1's disproven `_seed_bars` hypothesis was documented rather than erased.

### PW-GF-09: (M1)/(R) vs (M2)/(R) — the pair the single-element test couldn't show

| Pair | M extent (x) | R extent (x) | Overlap |
|---|---|---|---|
| (M1) vs (R) | [−34029, −21615], width 12414 | [−30611, −6597], width 24014 | **~9000 units**, ~73% of M1's width |
| (M2) vs (R) | [76335, 106593], width 30257 | [−30611, −6597], width 24014 | **0 — completely disjoint**, ~107,000 units apart |

Y-extent tells the rest of the story: `(R)` spans y=[3003, 78728] (75,725 units tall) — it stacks **elevation + 4 sections vertically in one canvas** (confirmed structurally from the earlier PDF reading: `PW-GF-09(R)` literally *is* "Elevation + 4 Sections"). `(M1)` spans only y=[2526, 10677] (~8,000 units) — one view's worth, sitting near **R's bottom-most (first) view**. `(M2)` — which is where the Dowel Bar Schedule and Insert Schedule actually live — sits in an entirely separate region of the coordinate space, sharing nothing with `(R)`.

Symbol offsets for (M1) vs (R), by label:

| Symbol | M1 | R | Distance |
|---|---|---|---|
| 1 | (−27818.3, 7183.3) | (−26506.4, 7215.9) | **1312mm** |
| 2 | (−29803.3, 7268.3) | (−27831.4, 6623.1) | **2079mm** |
| 3 | (−26177.9, 3650.4) | (−26177.2, 4661.9) | **1012mm** |

An order of magnitude looser than SS-GF-01's already-inconsistent offsets.

### PW-GF-02: (M1)/(R) vs (M2)/(R), plus a second confound

Same disjoint pattern for (M2) vs (R) (0 overlap; M2's x-max is 58841, R's x-min is 65788 — ~7000 units apart with no shared range). For (M1), a new problem appears: **`(M1)` contains 6 section-marker-symbol instances, not 3** — two separate `1`s, two separate `2`s, one `3` — because (per the PDF reading, `PW-GF-09(R)`'s own "TYPICAL FOR" note) this panel type repeats across multiple floors, and `(M1)` draws multiple erection-mark instances for those repeats on one sheet. `(R)` has exactly one `1`, one `2`, one `3` (it's typical for all instances, drawn once). **"Match symbol 1 on M to symbol 1 on R" is therefore not even well-defined here without first disambiguating which physical instance M's symbol belongs to** — a second, independent reason spatial matching can't be a simple nearest-symbol rule.

## Answering the five questions

**1. Do (M) and (R) always share the same coordinate frame?** No. Confirmed pattern across all 3 elements: the *single-view* mould sheet (`M`/`M1`) sits in rough proximity to the *first view* on the corresponding `(R)` sheet — never exact, offsets from 62mm to 2079mm even for same-labeled reference symbols, no consistent transform. The *schedule-bearing* mould sheet (`M2`, present wherever the element has one) shares **nothing** — different, non-overlapping region of the coordinate space, every time it was checked (2/2).

**2. Is the alignment exact, translated, rotated, or scaled?** None of these, cleanly. It is not exact (421mm max SS-GF-01 offset). It is not a single translation (the three SS-GF-01 offsets point in different directions, different magnitudes). Not enough matched points exist to fit rotation or scale reliably, and the PW-GF-09 offsets (1000-2000mm) are too large relative to panel width (~2000-24000mm) to be explained by a small rotation of a good base translation. The honest description is **"drafted independently, starting from a habitually similar real-world reference point,"** not registration.

**3. What geometric features make registration robust?** None identified as robust across this sample. Candidates tried and found unreliable: panel-outline (`A-FLOR`) bounding box (one coincidental exact number, not corroborated at the symbol level); section-marker symbols (inconsistent offsets, and not even uniquely defined where "TYPICAL FOR" repeats a panel). No feature in this drawing set behaved like a true fiducial marker.

**4. Under what conditions does it fail outright?** Two found, both structural, both reproducible: (a) **any sheet whose (R) counterpart draws multiple stacked views in one canvas** — the mould sheet only ever draws one of those views, so most of (R)'s coordinate space has no mould-sheet counterpart at all; (b) **any element repeated across floors ("TYPICAL FOR")** — the mould sheet for the repeated element carries multiple instances of what looks like one reference symbol, breaking any 1:1 matching assumption.

**5. Can a confidence score be computed for registration quality?** Only a low one, honestly. A candidate formula — normalized bounding-box overlap fraction between the (M)-sheet's extent and (R)'s extent — would correctly rank these 5 pairs (M1-type: 43-73% overlap; M2-type: 0%), which is a real, cheap, computable signal. But it answers "is there *any* chance of proximity-based correspondence for this sheet pair," not "are these two labeled points the same feature" — the symbol-offset data shows that even inside a genuinely-overlapping region, point-level confidence should stay low (hundreds of mm of noise, not millimeters).

## Revised standing on VQ-002

VQ-002 (SS-GF-01's N7 = T8@200mm, `docs/validation_questions.md`) is **not retracted, but downgraded**: the 11mm co-location is still the strongest single piece of corroborating evidence available for that question, but this audit shows it cannot be read as a high-precision confirmation — it sits well inside the ~62-421mm noise band measured on the same sheet pair. The candidate answer stands as a candidate; the confidence attached to it in `notes.md`/VQ-002 should read "plausible, weakly corroborated" rather than implying near-certainty. Updated below.

## What this means for the "smallest missing piece" conclusion

The N7 trace's proposed next step — treat cross-sheet spatial co-location as `supports`-polarity evidence once a shared frame is verified — **survives, but weakened and narrowed**. It survives because a bounding-box overlap check is real, cheap, and correctly separates "these two sheets might overlap" (M1-type, 2 of 2 tested) from "these definitely don't" (M2-type, 2 of 2 tested) — that binary signal alone would stop cross-sheet spatial evidence from being wasted effort on M2-type pairs, which is useful. It is narrowed because "verified shared frame → tight spatial match" is false: even where overlap exists, point-level distance should contribute at most **weak, low-confidence corroboration** (matching Phase 12's existing `spatial_distance` treatment — informational, never a qualifying signal on its own) — not the "layer fusion, everything can see everything else" simplification. The registration is not exact enough to bear that weight. Composing identity still requires the symbolic/evidence machinery Phase 12 already has; proximity narrows a search, it does not replace the search.

## What remains open

- Whether the ~400mm-scale noise is drafting tolerance (plausible — hand-adjusted repeated details) or an artifact of DWG→DXF conversion (ODA File Converter) has not been tested; a same-format comparison (if a project ever supplies matching DWG-DWG or DXF-DXF pairs) would isolate this.
- Whether a *rotation* exists that a 2-point fit didn't have enough symbols to detect remains untested — 3 points per pair is thin for that; more real projects, not more analysis of Apollo, would settle it.
- Whether this consultant's convention differs from others' is exactly the cross-project question the original message asked, and remains unanswerable with one project in the corpus.
