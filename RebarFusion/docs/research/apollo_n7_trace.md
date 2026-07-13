# Tracing one real bar: SS-GF-01's N7, by hand, through every drawing

**No code was written or modified.** This is the manual reasoning-chain exercise: reconstruct one physical bar exactly as an engineer would, from the actual Apollo drawings, then identify the smallest missing piece preventing the software from reproducing the reasoning. Every coordinate below was read from the real files this session (ezdxf over the DXF / ODA-converted DWG), not recalled.

## The bar

**N7** on element SS-GF-01 — the upstand reinforcement reference established in the Phase 12 research (N-code on the Mould sheet, adjacent to real S-RBAR U-bar geometry).

## The chain, step by step

### 1. Where the engineer starts: the (M) sheet names and places N7

`SS-GF-01(M).dxf` carries four annotation groups, each a stack of **dimension-row labels**: `LENGTH / UPSTAND / N1/N2 / N4 / N7 / N6` (e.g. group at x=78643: LENGTH at y=6700, UPSTAND 6300/5900, N1/N2 5500, N4 5100, **N7 4700**, N6 4300). These are not leader labels pointing at one object — they are **row headers for horizontal dimension chains**, one band per row, running across the section beneath them.

### 2. Where N7 *is*: read the N7 row's dimension chain

At the enlarged upstand detail (group x=90128), the N7 row (y≈4990) contains the chain:

```
50 | 220 | 255 | 500 | 500 | 255 | 220 | 50   = 2050
```

which sums exactly to the LENGTH row's 2050 (y=5790) — internal consistency check passed, the same check an engineer does instinctively. **This row is N7's placement specification**: the chain boundaries are the positions of the N7 bars along the 2050mm upstand — symmetric, as upstand U-bar legs would be. The UPSTAND row above it (150|725|300|725|150, y=5390) dimensions the upstand's own geometry. At the x=84345 group, N7's row reads `150 | 1750 | 150` (y=4367-4429) — same bar, different section, coarser placement.

So the (M) sheet alone gives: **name (N7), positions along the panel (the chains), the upstand context (row stack), and absolute level** (`100224 / GF SSL` at (78105,3773)). It gives **no diameter, no spacing designation, no bar size** — N-codes are reference codes (established, A5).

### 3. The hop the whole problem hinges on: (M) and (R) share a coordinate frame

This is the trace's central discovery, and it **falsifies an assumption**:

- Section-marker symbols `1`, `2`, `3` appear on **both** sheets at near-identical coordinates: `1` at (62710, 25398)ᴹ vs (62852, 25794)ᴿ; `2` at (67996, 24403)ᴹ vs (68020, 24460)ᴿ; `3` at (65996, 24403)ᴹ vs (65930, 24425)ᴿ.
- The `A-FLOR` panel-outline layer has **byte-identical extents** on both sheets: x-min 63183, y ∈ [2825, 27100], exactly. `S-RBAR` min corners agree to ~25mm.

**SS-GF-01(M) and SS-GF-01(R) are drawn on the same template at the same coordinates.** The engineer's "mental overlay" of mould sheet onto reinforcement sheet is not mental at all here — it is literal coordinate identity. Assumption **A12** ("no coordinate transform between views should be assumed") was written about *views within and across sheets in general*; it remains true for plan-vs-section-vs-detail placement, but it **over-generalized**: for same-element (M)/(R) sheet *pairs* in this drafting convention, the shared frame not only exists, it is the primary cross-referencing mechanism. The Phase 12/14 designs treated spatial distance as polarity-UNKNOWN corroboration precisely because no frame was assumed shared — for these sheet pairs, that threw away the strongest signal in the package.

### 4. Closing the loop: what the (R) sheet says at N7's location

At the x=84345 section group, (M)'s N7 row band sits at y=4429. On (R), at the same sheet location, the label **`T8 @200 mm` sits at (83584, 4440)** — inside the group's x-span (82144–84044), **11mm** from the N7 row band, in a shared frame where the panel is 2050mm+ across. Nothing else labels that band.

Corroboration at the other co-located group (x=78643) is weaker — (R)'s labels there sit lower in the section (y≈2.5–3.4k vs the N7 row at 4638) — and the enlarged x=90128 upstand detail is (M)-only ((R)'s geometry ends at x≈85.3k), so it cannot cross-check.

**Candidate conclusion (NOT asserted as truth): SS-GF-01's N7 = T8 @ 200mm** — 8mm diameter upstand U-bars at 200 centers, positioned per the N7 dimension chains. One strong co-location + one weak, in a proven shared frame. This goes to `docs/validation_questions.md` as **VQ-002** for engineer confirmation, not into ground truth.

### 5. The complete authority chain for N7, as the drawings actually distribute it

| Fact | Source | Where, exactly |
|---|---|---|
| Name / identity | (M) row labels | four groups, e.g. (78643, 4700) |
| Positions along panel | (M) N7-row dimension chains | 50\|220\|255\|500\|500\|255\|220\|50 at y≈4990, x=87826→89826 |
| Upstand geometry context | (M) UPSTAND row + drawn S-RBAR U-bars | x≈88–90.5k, y≈3–4.5k (rendered and verified in Phase 12 research) |
| Absolute level | (M) `100224 / GF SSL` | (78105, 3773) |
| Diameter + spacing | **(R) label at the co-located band** | `T8 @200 mm` at (83584, 4440) — pending VQ-002 |
| Quantity | derivable from the (M) chain boundaries | ~6–8 positions per upstand run — pending the same confirmation |
| Hook/bend detail | the (M)-only enlarged detail at x=90128 | drawn U-bar legs; no numeric hook callout found |
| Cover | **not found for this bar** | no cover dimension in either sheet's N7 context — honestly absent |
| Schedule row | **does not exist** | SS-GF-01 has no bar schedule in this package |

Note what this table does to the working hypothesis from two turns ago: the smallest missing piece for *this* bar is **not schedule parsing** — there is no schedule. The engineer closes the N7 loop through the **shared-frame overlay**, and would only reach for a schedule if the package had one.

## The smallest missing piece

The software already extracts everything the chain uses: dimension entities with defpoints and measurements (Phase 2), text with positions (Phase 2), S-RBAR geometry (Phases 3–7), cross-sheet observation pairs with computed spatial distances (Phase 12.2 — the N7↔T8 pair *already got* `spatial_distance` evidence at generation time).

What's missing is exactly one link: **the system never checks whether two same-element sheets share a coordinate frame, so cross-sheet spatial co-location is permanently stuck at polarity UNKNOWN and can never support anything.** The frame check itself is nearly free — compare `A-FLOR`-class layer extents between the pair (identical here to the millimeter); Phase 1's `DrawingRegistration` dataclass has sat empty since it was written, waiting for precisely this.

Smallest change, stated for a future implementation turn (not begun): (1) at Phase 1 or 12.1, verify shared-frame for same-`drawing_number` sheet pairs by outline-extent comparison, populating `DrawingRegistration.confidence`; (2) when — and only when — the frame is verified, cross-sheet `spatial_distance` evidence for that pair may carry `supports` polarity at co-location distances that are tiny relative to the panel (the tolerance question is RQ-6's, to be derived, not invented). No new phase, no new framework; one verification plus one polarity rule, measurable immediately against Apollo (the N6/N7↔T-mark pairs are sitting at REVIEW waiting for exactly this evidence).

What this would *not* solve, kept honest: PW-GF-09's dowel bars (N7/N8 there resolve through the (M2) schedule table, a genuinely different mechanism — the schedule-parsing gap is real too, just not the smallest piece, and not this bar's); hook numeric geometry (nothing in this package dimensions the upstand hook); cover (absent for this bar). One trace, one bar, one missing link — per the exercise's design.
