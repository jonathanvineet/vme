# Phase 9 — Engineering Family Builder: Initial Audit

Scope: `run_phase9.py`, `core/engineering/family.py`, `core/engineering/solver.py`, run against `SS-GF-01(M).dxf`. First pass — fixes for concrete, evidenced bugs, plus findings flagged for a decision rather than fixed unilaterally.

## Collateral fix — `run_phase9.py` crashed outright
Had its own duplicated copy of the old raw-ezdxf leader-scanning code (same pattern as `run_phase8.py` before that fix), so it crashed immediately (`AttributeError: 'tuple' object has no attribute 'tail'`) once `cluster_annotations` was updated to expect `Leader` objects. Fixed identically: now calls `reconstruct_leaders()`.

## Fix 1 — Hardcoded readiness gate (same class of bug as Phases 6 and 8)
`run_phase9.py:525` printed `"READY FOR PHASE 10: YES"` unconditionally. Fixed to gate on the three checks the script already computes and prints but didn't act on: families built, family QA generated, object membership deterministic.

## Fix 2 — Nondeterministic EngineeringObject UUIDs (new instance of the Phase 7.1 bug class)
`ConstraintSolver.solve()` (`core/engineering/solver.py`) assigned `uuid.uuid4()` to every `EngineeringObject.uuid` — random per run, inconsistent with the deterministic-UUID5 discipline used everywhere else in the pipeline (`NAMESPACE_NODE`, `NAMESPACE_EDGE`, `NAMESPACE_COMPONENT`, `NAMESPACE_IDENTITY`). Confirmed observable: ran `run_phase8.py` twice, same component's `EngineeringObject.uuid` differed between runs (`f815e699...` vs `390d36d3...`). Fixed with a `NAMESPACE_ENGINEERING_OBJECT` constant and `uuid5(NAMESPACE_ENGINEERING_OBJECT, str(comp_uuid))` — the object UUID is now a pure function of its source component, like everything else. Re-verified: identical across 3 consecutive runs after the fix, and `tests/determinism.py --runs 5` still reports 1 unique hash.

## Finding — family fragmentation: same mark, multiple families
5 families total in this drawing, but **both marks that produced multi-object families are split across more than one family**: `N4` across 2 families (4 members + 10 members), `N6` across 3 separate **single-member** families (each confidence 0.0, each missing diameter and spacing).

Traced the mechanism: `FamilyBuilder._group_family_seeds` keys seed grouping on `(mark, layer, recognition_type, round(orientation/10), round(length/100))`. `build_families` then repeatedly extracts one family per pass from a seed group and only continues if leftover seeds remain — so even seeds that land in the *same* bucketed key can still end up as separate families if `_discover_members`'s tighter geometric matching doesn't pull them together.

This traced into two distinct situations, not one:
- **N4's 2-family split looks like it could be legitimate**: the two representative seeds have matching profiles but the resulting families (4 members, 10 members) are plausibly two separate physical bar groups that happen to share a mark — a real, common scenario in structural drawings (the same mark reused in different areas). Not flagged as a bug without more evidence.
- **N6's 3-way singleton split looks like a real problem**, not a coincidence. Their profiles are genuinely different from each other (two `branch`-type components with very different lengths — 1964.8mm and 3227.8mm — plus one unrelated 56.2mm `straight_bar` at a different orientation), so the family builder correctly refused to merge them. But checking *why* all three carry the mark `N6` at all: only one of them (`0d40eb22`) has an actual `TOKEN_MARK=N6` association candidate, and it's weak — **score 0.40, a plain centroid-distance match at 1801mm, not a leader-pointer match**. The other two components in the "N6" group never appear as `TOKEN_MARK` candidates in the association data at all; they must be picking up the mark through the mark-propagation step in `FamilyBuilder._seed_bars` (which propagates diameter/spacing — and, it turns out, effectively mark identity — across same-mark bars). This suggests at least 2 of these 3 "N6" families may be spurious: either a weak/wrong Phase 8 mark association, or downstream propagation over-applying a mark to unrelated components. **Not fixed in this round** — this needs a closer look at `_seed_bars`'s propagation logic specifically, which I have not done yet.

## New informational report — cross-family shared marks
Per your direction (inform, don't silently block), added `cross_family_marks` — a simple mark → family-UUID-list map, computed in `run_phase9.py`, written to `debug/phase09/<drawing>/cross_family_marks.json` and the printed summary. It does not emit a QA warning or block the gate; it exists so the N4/N6 fragmentation above is visible rather than silently buried in per-family QA. On this drawing:
```
N4: 2 families
N6: 3 families
```
This is the Phase 9 equivalent of Phase 8's `summarize_marks()` — same non-blocking, informational pattern.

## Not yet implemented (explicitly deferred, not forgotten)
A **cross-family conflict check** (the `duplicate_family_mark` idea) — something that would actually flag it as an error when two families claiming the same mark have materially different diameter/spacing/type, versus two families that plausibly represent the same physical bar type split for no good reason. I did not implement this yet because it requires deciding the correct rule (what counts as "conflicting" vs "legitimately repeated"), and — per the N6 finding above — the more urgent question is whether the underlying mark *association* is even correct before building a rule on top of possibly-wrong data.

## Other numbers not yet investigated
- **Average Spacing Error: 94.663mm** — high relative to typical 150-200mm spacings; not yet traced to a cause.
- **Average Confidence: 0.276** — pulled down significantly by the three 0.0-confidence N6 singleton families; unclear yet what a "normal" confidence should look like here.
- **Standalone Summary** (`{'Branch': 5, 'Different type': 27, 'No nearby family': 1, 'Stirrup': 2, 'Different orientation': 3, 'Isolated': 4}`, 42 total) — not yet checked whether "Different type: 27" (the largest bucket) is correct or hiding a real family that should have formed.
- **Family QA warnings (12 total across 5 families)** — not inspected individually beyond the N6 ones above.

## Verification performed
- `tests/determinism.py test_project --runs 5`: 1 unique hash / 5 runs.
- `tests/regression.py test_project`: Phase 2/3/6/7 all pass; only the pre-existing, deliberately-open Phase 6 duplicate-edge item remains.

## Recommendation
Before trusting family output for Phase 10 reconstruction, the N6 mark-propagation question needs resolving — it's the one finding here that looks like an actual data-correctness bug (not just a design/ownership question like the duplicate-mark QA rule was). Suggest tracing `_seed_bars`'s diameter/spacing/mark propagation logic next, using the N6 case as the concrete reproduction.
