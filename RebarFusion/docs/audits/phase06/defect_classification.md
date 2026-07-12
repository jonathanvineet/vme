# Phase 6 — Orphan Node & Duplicate Edge Classification

Follow-up to `audit_phase06.md`, after tightening the validation gate (`core/topology/builder.py::_stage_6_7_validation`) to distinguish critical / error / warning / info instead of collapsing everything into critical/warning. This classifies every one of the 87 orphan nodes and 19 duplicate edges found in the original audit, per the plan: don't fix blindly, explain first.

## Orphan nodes: 87/87 explained — all expected, zero topology bugs

Method: cross-referenced each degree-0 node's `connected_entities` against the set of ARC-center and CIRCLE-center points computed the same way `node_builder.py` computes them.

| Count | Source | Layer |
|---|---|---|
| 33 | ARC center only | S-RBAR |
| 20 | ARC center + CIRCLE center (coincident) | S-RBAR |
| 15 | CIRCLE center only | S-RBAR |
| 10 | ARC center only | A-GENM |
| 4 | ARC center only | A-FLOR |
| 3 | ARC center only | G-ANNO-SYMB |
| 2 | CIRCLE center only | A-DETL-MBND |

**Root cause, not a bug**: `node_builder.py` registers a node at every ARC's center and every CIRCLE's center (for spatial indexing), but `TopologyBuilder._stage_6_1_build_edges` never uses those center points as edge endpoints — arcs connect via their start/end angle points, and circles produce no edges at all (this is explicit in the code, `builder.py` line 90-91: *"CIRCLES are typically single-node closed loops... We'll skip standalone circles as structural graph edges"*). A center point therefore has 0 incident edges by construction, on every drawing, always. This is exactly why Phase 5's own "no orphan nodes" check never caught it — Phase 5 checks for nodes with no `connected_entities` at all, which is a different (weaker) condition than "has 0 topological edges." Both phases were individually correct; the disconnect was in what each one was actually checking.

**Fix applied**: `_stage_6_7_validation` now computes the ARC/CIRCLE center node set explicitly and reports orphans in that set as `info` (not `error`/`warning`). Any orphan node **outside** that set — i.e. an actual LINE/POLYLINE endpoint or ARC start/end point with no connection — is now flagged as an `error`, since that would be a genuine topology defect. On the current drawing, that count is **0**.

## Duplicate edges: 19/19 traced to source geometry, none are graph-building bugs

Method: for each duplicate node-pair, pulled both edges' `CanonicalProvenance` (source DXF handle, source block name).

**Group A — 6 pairs, cross-layer, distinct DXF handles, no block:**
- 2× `A-FLOR` line duplicated by an `A-DETL-THIN` line (handles C7/322, CA/324) — floor line traced by a thin detail line
- 4× `S-RBAR` line duplicated by an `A-DETL-MBND` line (handles 128/338, 1EE/337, 1F1/33B, 350/3D5) — a rebar segment traced by a bend-mark/detail annotation line

This is a plausible, common drafting convention: an annotation/detail line drawn directly on top of structural geometry to mark a bend or highlight a floor edge. **Not evidence of a pipeline bug** — two distinct, intentionally-authored DXF entities that happen to be geometrically coincident.

**Group B — 9 pairs, same layer, from block `Detail View - M_Section Head - Filled SHOP DWG-600895-Elevation Top`:**
- Handle pair C84/C92 (LINE, `G-ANNO-SYMB`) recurs across **4** different insertions of this block
- Handle pair C8D/C99 (LINE, `G-ANNO-SYMB`) recurs across **4** different insertions
- Handle pair C85/C86 (ARC, `G-ANNO-SYMB`) recurs across **3** different insertions

Same block-internal handles repeating at multiple, independent node-pairs means the block **definition itself** contains two coincident lines (and a coincident arc pair). Given the block name includes "Filled," the most likely explanation is a filled-symbol authoring pattern — one line/arc for the visible stroke, one coincident line/arc as a hatch/fill boundary. Every insertion of the block reproduces the same internal duplication. This is a property of the symbol library, reproduced faithfully by Phase 3's INSERT explosion — **not a pipeline bug**, though it does mean any future recognition step needs to be aware that annotation symbols in this drawing carry doubled boundary geometry.

**Group C — 4 pairs, `A-FLOR` arcs, sequential native handles, no block (D0/D1, D2/D3, D4/D5, D6/D7):**
Each pair shares an identical radius/length (78.54, a quarter circle) and adjacent handle numbers, with no block involvement — i.e., drawn directly, not from an inserted symbol. This is the one group I can't fully explain from the data alone: it's consistent with either (a) an intentional convention (e.g. two arcs used together to represent a door swing symbol) or (b) an authoring accident (accidental duplicate-paste in the original DXF). **This needs a domain/CAD-literate call, not a pipeline fix** — the geometry pipeline is faithfully reproducing what's in the source file either way.

## Net result

- **Orphan nodes**: fully resolved as a validation-definition issue, not a data or topology bug. Fixed in code (see `audit_phase06.md` verdict update).
- **Duplicate edges**: all 19 trace to genuine source-DXF geometry (coincident annotation-over-structure lines, or duplicated boundary geometry baked into one specific symbol block), not to a defect in `TopologyBuilder`. 15 of 19 (Groups A+B) look like legitimate/explainable drafting conventions. 4 of 19 (Group C, the `A-FLOR` door-arc-looking pairs) remain ambiguous and are flagged for a domain call.
- Per the gate now in place (`core/topology/builder.py`), these 19 duplicate edges are still classified as `errors` and the pipeline correctly reports **NOT READY FOR PHASE 7** until a decision is made on whether to (a) accept Group A+B as permanently expected and encode that as an explicit allowlist (e.g. by layer-pair or by source block name), downgrading them to `info`, while keeping Group C as a hard error pending the domain call, or (b) leave all 19 as hard errors until each is individually confirmed.

## Recommendation
Don't silently downgrade any of these without a decision — that would recreate exactly the problem this audit was trying to fix (permissive gates masking real questions). Suggested next action: get a structural/drafting-literate answer on the 4 `A-FLOR` arc pairs (Group C); if confirmed intentional (e.g. a standard door-swing convention), encode the specific layer/pattern as an explicit, documented exception rather than a blanket duplicate-edge allowance.
