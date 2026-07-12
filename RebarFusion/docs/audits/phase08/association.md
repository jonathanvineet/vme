# Phase 8 — Engineering Association Engine: Initial Audit

Scope: `run_phase8.py`, `core/recognition/annotations.py`, `core/engineering/association.py`, `core/engineering/validation.py`, run against `SS-GF-01(M).dxf`. This is a first pass (gate fix + one integration bug + root-cause tracing of the annotation-resolution shortfall), not yet the same exhaustive gallery-based audit given to Phases 6/7.

## Fix 1 — Hardcoded readiness gate (done)
`run_phase8.py:187` printed `"READY FOR PHASE 9: YES"` unconditionally, regardless of the validation check printed one line above it (which could say `FAIL`). Same class of bug as the original Phase 6 gate, but with zero conditionality at all. Fixed: gate is now `annotations_ok and critical_qa_warnings == 0`, using the `QAWarning.severity` field that already existed in `EngineeringQAValidator` but wasn't being read. Current honest result on this drawing: **NO** (58 unresolved tokens).

## Fix 2 — "symbol" label leak into engineering objects (done)
`EngineeringAssociationEngine.find_group_candidates` excludes components labeled `['unknown', 'dimension', 'structural_outline']` from candidacy — a list that predates the Phase 7.5 audit. It was never updated when that audit added the new `"symbol"` label (regular-polygon CAD markers, confirmed non-rebar). Consequence: **25 of the 32 `symbol` components — CAD markers we specifically proved are not rebar — were being instantiated as `object_type: 'Bar'` engineering objects**, 25 of the 79 total (31.6%) reported "Engineering Objects" before this fix. Fixed by adding `'symbol'` (and `'leader'`, defensively, since it's annotation geometry not a bar) to the exclusion list. After the fix: engineering objects dropped 79 → 59, components-associated dropped 12.1% → 9.1% — both decreases are correct, not regressions, since the removed objects were confirmed non-rebar.

## Root cause found (not yet fixed) — leader tracing uses raw single-line segments, not the full leader shape
`run_phase8.py` builds its `leaders` list by scanning the DXF for every raw `LINE` entity on layer `G-ANNO-TEXT` and treating each one, independently, as its own 2-point leader (`p1`=start, `p2`=end, farther-from-text end assumed to be the "pointer tip" toward the bar).

But the Phase 7.5 recognition audit already established that `G-ANNO-TEXT` "branch" components are **3-line leader arrowheads** (one shaft + two short barbs meeting at a point) — 24 of them, confirmed visually. 24 × 3 = 72, which is exactly the leader count this script reports (`total leaders (G-ANNO-TEXT lines): 72`). So instead of tracing one true leader per arrowhead (text → shaft → arrowhead tip at the bar), the parser treats all three of its lines — including the two tiny barbs — as three separate, independent "leaders," each contributing its own (often meaningless) pointer-tip estimate.

Evidence, sampled from the 58 unresolved tokens (in groups that have a leader and real mark/length tokens, not empty text):

| Group | Computed leader tip → nearest S-RBAR | Text centroid → nearest S-RBAR |
|---|---:|---:|
| N1/N2 upstand group | 2786mm | 2396mm |
| N4 group | 2387mm | 1718mm |
| N7 group | 1987mm | 1212mm |
| N6 group | 1589mm | 982mm |
| next group | 1564mm | 764mm |

In every sampled case, **the raw text position is closer to the actual rebar than the computed "leader pointer tip."** A correct leader should point *at* the bar, i.e. end up closer than the text, not farther. This confirms the pointer-tip computation is picking up noise from barb segments rather than the true leader path, and explains the bulk of the 58 unresolved tokens: `find_group_candidates` searches within 1200mm of the (wrong) leader tip and, at 1200-2800mm actual distance to any real rebar, finds nothing.

This is a real design gap, not a one-line fix — it needs the leader arrowhead's 3 lines to be recognized as one shape (which Phase 7 already does — it's the `branch` label) and the true distal tip (the shaft's far end, away from the barb) identified, rather than iterating raw unlinked LINE entities. I have not implemented this yet since it's a more involved change to leader construction than the two fixes above, and per the established pattern on this project I want to confirm approach before writing it.

## Current state after the two applied fixes

```
Annotations Parsed       : 63.3%
Components Associated    : 9.1%
Engineering Objects      : 59
Average Confidence       : 0.52
Unresolved Tokens        : 58
QA Warnings              : 4 (0 critical)
READY FOR PHASE 9         : NO   (honest, was hardcoded YES before)
```

## Not yet audited
- The 8 groups with zero parsed tokens at all (parser coverage gap — e.g. does `AnnotationParser`'s regex vocabulary cover the actual text vocabulary in this drawing? Not yet checked).
- The 71 *resolved* groups / 100 resolved tokens — no accuracy check yet on whether the association is spatially *correct* (nearest S-RBAR component within radius isn't necessarily the *intended* one if multiple bars are nearby), only that a candidate was found at all.
- `build_constraints`' fixed `score >= 0.5` threshold, and the constraint solver (`core/engineering/solver.py`) itself — not yet read or audited.
- The 4 QA warnings (all `WARNING` severity, not `CRITICAL`) — not yet inspected individually.

## Recommendation
Fix the leader-tracing root cause before doing a deeper pass on the resolved-group accuracy, since a large share of the "unresolved" 58 tokens are very likely real, legitimate annotations (marks + lengths near an upstand detail) that should resolve once the leader tip is computed correctly — this is probably the single highest-leverage remaining fix in Phase 8, analogous to what layer-gating was for Phase 7.
