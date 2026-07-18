# Decoded Bar Bending Schedule (BBS) rules — VME Precast / ES Structural

Learned by reconciling the itemized BBS PDFs (`PW-GF-02.pdf`, `PW-GF-09.pdf`)
row-by-row against the raw DWG content. Every rule below was verified
numerically against **both** panels' BBS documents.

## Rule 1 — Unit weight
`unit_wt (kg/m) = d² / 162` with d in mm. Verified for every diameter the
BBS uses, including the odd `T15` row (15²/162 = 1.389, printed as 1.389).

## Rule 2 — Cover
Concrete cover is **30 mm** at every face/end. Straight bar length =
`clear extent − 2×30mm`:
- full-width bar: PW02 `3.70 = 3.760 − 0.06`, PW09 `3.94 = 4.000 − 0.06`
- full-height bar: both panels `2.87 = 2.930 − 0.06`

## Rule 3 — Bend deduction
`stated Length = Σ(shape segments A..F) − n_bends × 2d`
- open shapes: `n_bends = n_segments − 1`
  (verified: 2-seg → 2d, 3-seg → 4d, 5-seg → 8d, across T8/T10/T12/T16/T20)
- the standard closed tie (6 segments incl. hooks): deduction = **16d**
  (identical 0.632m tie row in both panels: Σ=0.760, −16×0.008)

## Rule 4 — Standard shapes (this drawing office)
- **UBAR / hairpin** (`T8 UBAR @pitch` callout): segments `0.4 / web / 0.4`
  where `web = thickness − 2×cover` (=100mm at t=160). Legs are a fixed
  400mm — a lap/development choice, not derivable from panel geometry.
- **Closed tie** (`T8 Ties @100mm` callout): 6 segments
  `0.08/0.1/0.2/0.1/0.2/0.08` = a 100×200mm core loop (column core =
  cross-section minus 30mm cover each side) with 80mm hook tails.
- **Edge U (horizontal)**: `0.6 / span / 0.6` — 600mm legs both ends.

## Rule 5 — Counts
- **Pitched runs**: `count = floor(run_extent / pitch) + 1` per labelled run.
  Tie runs span the column height 2.87m at 100c/c → **29 per run**.
  - PW09: BBS 174 ties = **6 runs × 29** (6 `Ties` callout instances)
  - PW02: BBS 58 ties = **2 runs × 29** (the two vertical panel edges)
- **Explicit `N -T{d}` callouts are literal and additive**: sum N over
  callout instances (in the elevation; section views repeat the same bars).
  - PW02 crack bars: `4-T16`×2 + `2-T16`×4 = **16** = BBS count exactly
  - PW09 crack bars: `2-T12`×4 = **8** = BBS count exactly
- Mesh with a pitch callout (`T8 @150mm`) doubles across the two faces
  (panels carry mesh at two z-planes ≈ 42/118 in a 160 panel).

## Rule 6 — Aggregation
BBS rows aggregate by (shape, dia, length): `Total Length = N × Length`,
`Weight = Total Length × unit_wt`. Grand total = Σ rows.

## Known document quirks
- PW-GF-09 BBS has a `T15` row (2 bars, 2.7m) — not a standard size; treat
  as data-entry for T16 (most likely) but keep its 7.5kg visible.
- The (R)-sheet "Summary Schedule" table does NOT match the BBS totals
  (PW02: 369.2 vs 319.0; PW09: 373.6 vs 390.9). The BBS is the itemized
  fabrication document; the Summary Schedule appears to include/exclude a
  different bar population (e.g. projecting/dowel allowances). When both
  exist, reconcile per diameter, not just totals.
