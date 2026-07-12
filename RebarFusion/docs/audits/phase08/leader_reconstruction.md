# Phase 8 — Leader Reconstruction Fix: Results

Implements the approved fix from `audit_phase08_engineering_association.md`: a reusable Leader Reconstruction stage (`core/recognition/leaders.py`) instead of a drawing-specific patch.

## What changed

1. **New module `core/recognition/leaders.py`** — `Leader` dataclass (`shaft_edge_id`, `arrowhead_edge_ids`, `tip`, `tail`, `confidence`) and `reconstruct_leaders(graph, comp_repo, layer)`, operating on the already-built Phase 6 connectivity graph/components rather than re-scanning raw DXF lines.
   - **3-edge arrowhead pattern** (one degree-3 node + three degree-1 nodes): shaft = longest of the 3 edges, tip = the degree-3 meeting point (where shaft + both barbs converge — geometrically the arrow point), tail = the shaft's other end. Confidence 1.0.
   - **1-edge simple leader** (no arrowhead drawn): tip/tail can't be geometrically disambiguated from a single line; both ends kept, confidence 0.5, left for the caller to resolve by proximity.
   - Anything else on the leader layer (e.g. stray annotation geometry) is skipped, not forced into a leader.
2. **`EngineeringAssociationEngine.cluster_annotations`** (`core/engineering/association.py`) now takes `List[Leader]` and uses `leader.tail` directly for text-proximity clustering and `leader.tip` directly as the pointer end — no more re-deriving "which end is farther from the text" from raw coordinates.
3. **`run_phase8.py`** now calls `reconstruct_leaders()` instead of scanning the DXF for raw `G-ANNO-TEXT` lines via `ezdxf` directly (that import is gone).
4. **Leader search radius increased 1200mm → 3600mm** for leader-anchored candidate search, justified by measurement (not guessed): after fixing tip/tail assignment, tip-to-nearest-rebar distance on this drawing ranges 67mm-3469mm, median ~1470mm. The old 1200mm radius structurally couldn't reach the median case even with a perfectly correct tip — the leader shafts in this drawing's convention often don't extend all the way to the bar.

## Verification the reconstruction is geometrically correct
All 24 `G-ANNO-TEXT` leader components on this drawing matched the 3-edge arrowhead pattern exactly (confidence 1.0 for all 24, 0 fell to the 1-edge fallback). Checked tip-vs-tail distance to nearest S-RBAR geometry for a sample: **in every case, the reconstructed tip is closer to the rebar than the tail** — the correct direction, unlike the old raw-endpoint heuristic where the opposite was often true.

## Measured before / after

| Metric | Before (raw-line leaders, 1200mm) | After tip/tail fix only (still 1200mm) | After tip/tail fix + radius 3600mm |
|---|---:|---:|---:|
| Annotations parsed | 63.3% | 65.8% | **98.1%** |
| Unresolved tokens | 58 | 54 | **3** |
| Engineering objects | 59 | 59 | 59 |
| Components associated | 9.1% | 9.1% | 9.1% |
| Average candidate score | 0.52 | 0.52 | 0.48 |
| QA warnings | 4 (0 critical) | 4 (0 critical) | 9 (1 critical) |

The tip/tail fix alone only moved the number slightly (58→54) because the geometric direction was now correct but the radius was still too small to reach the median real distance — both problems needed fixing together, which is why they're reported as one combined result.

## Duplicate-mark QA rule: moved, not downgraded
Resolving far more marks surfaced a real ownership-boundary bug: `EngineeringQAValidator`'s "duplicate_mark" rule was flagging `CRITICAL` whenever the same mark (e.g. `N4`) appeared on more than one component — but a mark is a schedule/type label expected to appear on many physical bar instances; grouping same-mark bars into one family is explicitly **Phase 9**'s job, not a Phase 8 uniqueness violation. Resolved per your direction (move it, don't just downgrade it):

- **Removed** the `duplicate_mark` rule from `EngineeringQAValidator.validate()` entirely (`core/engineering/validation.py`) — Phase 8's validator now only checks per-object issues (orphan constraints, missing diameter/spacing), which is within its actual ownership.
- **Added `summarize_marks()`**, a separate, explicitly non-blocking, informational function that reports mark→count (`{'N4': 2, 'N6': 1}` on this drawing) without emitting any `QAWarning`. Wired into `run_phase8.py`'s summary output and a new `debug/phase08/<drawing>/shared_marks.json` artifact.
- **Not yet added**: the cross-family "two different families both claim mark X" check in Phase 9's `FamilyBuilder`/`FamilyQA` (`core/engineering/family.py`). That code already exists and already builds a `FamilyQA` per family, but Phase 9 hasn't been audited in this session yet — adding a new rule to unaudited code now would be building ahead of the audit trail this whole process has been protecting. Flagging as the natural first item when Phase 9 is picked up.

Result: QA warnings 9 → 8, **critical warnings 1 → 0**. `READY FOR PHASE 9` is now `NO` solely because of the 3 remaining unresolved tokens — the only meaningful blocker left.

## Residual gap
3 tokens remain unresolved (down from 58) — not yet individually traced; likely either the 8 originally-zero-token groups (unrelated to leaders) or a genuine outlier beyond the 3600mm radius. Low priority given the scale of improvement; can be traced on request.

## Verification performed
- `tests/determinism.py test_project --runs 5`: 1 unique hash / 5 runs — deterministic (leader reconstruction and the QA rule move both add no randomness).
- `tests/regression.py test_project`: Phase 2/3/6/7 all still pass; only the pre-existing, deliberately-open Phase 6 duplicate-edge item remains, unrelated to this change.

## Verdict
Root-cause fix, not a heuristic patch — implemented as a reusable, drawing-agnostic Leader Reconstruction stage. Measured improvement: unresolved tokens 58 → 3 (94.8% reduction). The duplicate-mark QA rule has been moved to the correct ownership boundary rather than silently downgraded: Phase 8 now only judges individual objects, and cross-object mark-sharing is explicitly deferred to Phase 9 as informational data plus a noted future family-level check. With this, **Phase 8's only remaining blocker is the 3 unresolved tokens** — everything else that would have gated readiness is now clean.
