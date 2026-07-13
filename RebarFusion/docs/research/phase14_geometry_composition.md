# Phase 14 — Multi-View Geometry Composition Engine (research, pre-implementation)

**No code was written for this task. No architecture was modified. No frozen phase was touched.** Research only, per instruction.

**Roadmap note**: `docs/roadmap.md` previously slotted Phase 14 as Engineering Semantics. Per this task, Phase 14 is now **Multi-View Geometry Composition** and semantics shifts to Phase 15 (roadmap updated alongside this document). The standing gate still applies: *implementation* of this design must wait until the benchmark can measure it — which, as §10 shows, requires a corpus extension (geometric ground truth) that does not exist yet. This document is the design that gate was built to protect.

---

## 0 — Audit of the current reconstruction architecture (first task, before any design)

What exists, verified by reading the frozen modules — not from memory:

| Component | What it does today | Verdict for Phase 14 |
|---|---|---|
| `core/reconstruction/models.py::BarPath` | Centerline as `points: List[Point3D]` + `bends: List[BarBend]` + `hooks: List[BarHook]` + `closed`, with **geometry-recovery provenance already built in** (`recovery_method`, `recovery_confidence`, `truncated_branch`, `recovery_notes`) | **Reuse as the per-fragment representation.** The provenance discipline Phase 14 needs already exists here at single-drawing granularity — extend the *pattern*, keep the type. |
| `models.py::BarBend`, `BarHook` | Bend = vertex + angle + radius; Hook = end + angle + length | **Reuse unchanged.** The composed bar's hooks/bends use these exact types. Today they exist but are **never populated from detail views** — `bar_builder` has no source for them (confirmed: no writer of `hooks` outside path recovery). This is precisely the gap composition fills. |
| `geometry_recovery.py::recover_bar_path` | Walks the real connectivity graph within ONE component (`simple_path`/`closed_loop`/`longest_path_in_branch`/`fallback_straight`) | **Reuse unchanged as the fragment extractor.** Phase 14 does not replace single-drawing recovery; it consumes its output per contributing drawing. |
| `bar_builder.py::PhysicalBarBuilder` | One `PhysicalBar` per family member: representative path + member offset; honest diameter provenance (`diameter_source`/`diameter_confidence`) | **Reuse the provenance pattern; the builder itself gets a sibling, not a replacement.** Today's builder is the single-drawing path; composition is a new entry point that produces the same `PhysicalBar` type from multi-drawing input. |
| `assembly_builder.py` `_z_for_family`/`_layer_z_offset` | Z positions from **heuristic layer stacking** (diameter-derived offsets), not from drawings | **The weakest link found by this audit.** Z is currently *invented* — the one place the frozen pipeline fabricates geometry. Composition replaces this with elevation/section-sourced Z where evidence exists, and must downgrade, not hide, the heuristic where it doesn't (see §3, §9). |
| `tube_sweep.py`, `mesh_builder.py`, `triangulator.py` | Centerline → mesh (parallel transport frames) | **Reuse unchanged, downstream.** Meshing is aspect-agnostic; it doesn't care whether the centerline came from one drawing or five. |
| Phase 12 (`core/fusion/`) | `PhysicalIdentity` with `Claim`s (facts per observation), `ResolutionDecision`s, evidence categories/polarity, REVIEW discipline | **The required upstream input.** Composition operates ONLY on resolved identities — never on raw cross-drawing observations (that would re-open the identity question inside geometry, the exact mistake the Phase 12 research forbade). |
| `docs/engineering_assumptions.md` A7-A11 | Per-aspect view-authority table (which view is trusted for which fact) | **This is the authority matrix's seed** — already written, already evidence-tagged. §2 extends it; it is not reinvented. |

**Must remain frozen**: Phases 1-13 entirely. Composition is a new stage between Phase 12's output and Phase 10's meshing, reusing Phase 10's types and recovery — architecturally a *new caller* of frozen code, not a modification of it.

**Must be replaced (eventually, by this design)**: only `assembly_builder`'s invented Z-offsets — and even that by *supersession* (composed bars carry evidence-based placement; the heuristic remains as the explicitly-labeled fallback), not by editing the frozen module.

---

## 1 — How a human engineer reconstructs one bar from five drawings

Observed engineer behavior, grounded in the Apollo package (the PW-GF-09 sheet set read in full during Phase 12 research):

1. **Fix identity first.** "Which bar am I building?" is answered before any geometry is touched — via mark, schedule row, and callout symbols. (Phase 12 already models this; composition assumes it done.)
2. **Take the path from the view that draws it to scale.** The plan/elevation gives the bar's run — its XY extent, where it starts and stops relative to panel edges. The engineer traces the drawn line, reading dimension chains for exact values where the drawing is schematic.
3. **Take the cross-section story from sections.** Where the bar sits through the thickness (near face / far face / centered), cover, and how it relates to the other layers. The engineer does NOT get the bar's length from a section — sections are authoritative *perpendicular to* the cut, schematic *along* it.
4. **Take end treatment from details.** Hook angle, bend radius, anchorage length come from the detail sketch its callout points to — applied to the specific end the callout marks, never to both ends by default.
5. **Take counts and sizes from the schedule.** Diameter, quantity, cut length. When the schedule's cut length disagrees with the plan-measured length, the engineer does not average — they know cut length includes hook/bend allowances and reconcile *by model* (straight length + bend deductions), or flag the discrepancy.
6. **Compose by aspect, not by overlay.** At no point does the engineer spatially register the five drawings. Each view answers the question it is authoritative for; the bar is the sum of the answers. Conflicts between views are *findings* (drawing errors, revision skew) — reported, never silently resolved.

The machine version of this is therefore **aspect-wise composition over a resolved identity** — the same conclusion the Phase 12 research reached in outline (Addendum 1's per-aspect authority table); this document is that table taken to full depth.

## 2 — Authority matrix

Extends `engineering_assumptions.md` A7-A11 (kept in sync — that file remains the single source of truth; this is the composition-specific expansion). "Authoritative" = the composed bar takes this aspect from this source when present; "corroborating" = checked against the authoritative value, mismatches become conflicts (§5), never inputs.

| Aspect | Authoritative source | Corroborating | Never a source | Evidence basis |
|---|---|---|---|---|
| XY path (run, in-plane shape) | Plan / elevation with to-scale geometry (`recover_bar_path` on the identity's plan-view observation) | Detail sketch local shape at attachment locus; schedule cut-length (via bend-deduction model only) | Section (schematic along the bar); schedule directly | A8; Phase 10.1 recovery philosophy |
| Z position / through-thickness placement | Section (drawn position + cover annotation) | Elevation level tags (`GF SSL` + dimension chains) for absolute Z | **Layer-stacking heuristic** — permitted only as explicit `placement_source='heuristic_layer_stack'`, confidence-capped | A10; §0 audit finding on `_z_for_family` |
| Diameter | Self-decoding mark / schedule row (Phase 12 Claim) | Section's drawn circle at true scale | Visual fallback (exists in Phase 10 as `missing_visual_fallback`, correctly labeled) | A4, A7; Phase 10.0 finding 10F |
| Spacing, quantity | Schedule / spacing annotation | Detected member count from geometry | Inferred from gaps alone when annotation exists | A11; Phase 9.3 |
| Hook (angle, length, which end) | Detail view via callout → `AttachmentPoint` locus | Plan's local direction change at that locus | Default hooks "because bars usually have them" | A9; research report Addendum 1 |
| Bend (vertex, angle, radius) | To-scale path geometry (bends are *in* the recovered polyline); detail for radius when dimensioned | Schedule shape-code, if present | Smoothing/inference from noisy vertices | Phase 10.1 |
| Splice / lap (position, length) | Detail / explicit annotation ("LAP 40d", dimensioned lap zones) | Two same-mark paths overlapping in one to-scale view (candidate signal only) | Assumed at panel joints without annotation | none in Apollo yet → **RQ-2 (§11)** |
| Cover | Section dimension / general notes ("Wall 30mm, Corbel 25mm" — read on PW-GF-09(R)) | — | Hardcoded defaults (`CoordinateFrame.cover=40.0` today — flagged) | A7 evidence; audit §0 |
| Continuity across elements ("continues into P4") | Explicit annotation / typical-note | — | Geometric proximity across drawings | A12; RQ-3 |

## 3 — What is never inferred

Engineering facts requiring explicit drawn/written evidence — absence means the composed bar records the aspect as **absent**, with the reason, exactly like `ObservationFact`'s invariant one level up:

- Diameter, spacing, quantity, mark (Phase 12 Claims only).
- Hook existence, hook angle, hook length, **which end a hook is on**.
- Bend radius (a polyline vertex proves a bend's existence and angle; radius needs a dimension or detail).
- Splice/lap existence, position, and length.
- Cover values.
- Z position through thickness (the current layer-stack heuristic is *permitted to survive* only as an explicitly labeled, confidence-capped fallback — it may never be laundered into looking evidence-based).
- Continuity into another element; termination type (bearing, anchorage, cut).
- Anything from a view that isn't authoritative for it (a section never contributes run length; a schedule never contributes position).

Corollary (the composition invariant, mirroring Phase 12.1's observation invariant): **a `GeometryAspect` is only present in the composition when a `GeometryFragment` from an authoritative source supplied it. No aspect is ever emitted with a placeholder value.** A composed bar with no hook evidence has zero hook aspects — not a hook with `angle=None`.

## 4 — Internal representation (design only, no code)

```python
@dataclass
class GeometryFragment:
    """One drawing's geometric contribution to one resolved identity --
    the bridge object between a Phase 12 PhysicalIdentity's observation
    and Phase 10's recovery machinery. Wraps the EXISTING RecoveredPath/
    BarPath output for that observation's component(s), unmodified, plus
    which view produced it."""
    uuid: UUID
    identity_uuid: UUID                # Phase 12 PhysicalIdentity -- composition NEVER
                                        # groups fragments itself (§8)
    observation_uuid: UUID
    source_drawing: str
    drawing_role: str                  # from Phase 12.1's DrawingRole
    view_authority: List[str]          # aspects this fragment MAY contribute, from the
                                        # authority matrix -- assigned by rule, not per-case
    recovered_path: Optional[BarPath]  # reused Phase 10 type, with its recovery provenance
    local_frame_only: bool = True      # fragments live in their own drawing's coordinates;
                                        # composition never registers frames (A12)


@dataclass
class GeometryAspect:
    """One authoritative geometric fact contributed by one fragment.
    The composition-level analogue of ObservationFact: presence IS the
    claim; there is no aspect with an empty value."""
    uuid: UUID
    aspect: str            # 'xy_path' | 'z_placement' | 'hook' | 'bend_radius' |
                            # 'splice' | 'cover' | 'diameter' | ...  (closed vocabulary,
                            # only aspects with a real extractor -- HOOK enters this list
                            # only when a detail-view extractor actually exists)
    value: Any
    locus: Optional[str]    # 'start' | 'end' | 'bend_n' | 'whole_bar' -- AttachmentPoint
                             # semantics from the Phase 12 research, now load-bearing
    fragment_uuid: UUID
    confidence: float       # derived from the fragment's recovery_confidence and the
                             # source claim's confidence -- never invented
    source_entity_uuids: List[UUID]   # CAD-level provenance, same discipline as ObservationFact


@dataclass
class CompositionEvidence:
    """Why an aspect was taken, corroborated, or conflicted -- the
    composition-level Evidence, same shape/polarity discipline as Phase
    12.2/12.3 (supports / contradicts / unknown; no invented scores)."""
    uuid: UUID
    rule: str               # 'authoritative_source' | 'corroboration_match' |
                             # 'corroboration_conflict' | 'authority_absent_fallback'
    polarity: str
    description: str
    aspect_uuid: UUID
    confidence: Optional[float]


@dataclass
class GeometryComposition:
    """The decision record: which aspects were selected for one identity,
    which conflicted, what fell back. Mirrors ResolutionDecision's role in
    Phase 12.4 -- the composed bar stays clean; the composition explains
    how it was built. status uses the same PENDING/ACCEPTED/REVIEW
    vocabulary; a composition with any unresolved conflict is REVIEW and
    produces a bar only in explicitly-flagged draft form (or not at all --
    open design choice, RQ-5)."""
    uuid: UUID
    identity_uuid: UUID
    selected_aspects: List[UUID]
    conflicts: List['GeometryConflict']
    evidence: List[CompositionEvidence]
    status: str


@dataclass
class GeometryConflict:
    """Two fragments asserting incompatible values for one aspect.
    Never averaged, never auto-picked -- carries both values, both
    provenances, and the tie-break rule that WOULD apply (revision,
    authority rank) if a human confirms it."""
    aspect: str
    value_a: Any
    fragment_a: UUID
    value_b: Any
    fragment_b: UUID
    applicable_tiebreak: Optional[str]   # e.g. 'higher_revision_wins (A16)' -- stated, not applied
    requires_review: bool = True


@dataclass
class PhysicalBarGeometry:
    """The composed result. Deliberately as boring as PhysicalIdentity:
    a centerline (existing BarPath type), hooks/bends (existing types),
    placement, and a pointer to the composition that built it. No scores,
    no evidence, no conflicts on the bar itself. Feeds the UNCHANGED
    Phase 10 tube sweep / mesh builder."""
    uuid: UUID
    identity_uuid: UUID
    composition_uuid: UUID
    centerline: BarPath                 # reused
    placement_source: str               # 'section_evidence' | 'elevation_levels' |
                                         # 'heuristic_layer_stack' (capped, explicit)
    aspect_provenance: Dict[str, UUID]  # aspect name -> GeometryAspect that supplied it
```

Reuse summary: `BarPath`/`BarBend`/`BarHook` unchanged; Phase 12's `Claim`/`Evidence`/status vocabulary reused as patterns; `PhysicalBar` remains the mesh-facing type (a composed bar populates it via the same fields, with `placement_source` added rather than repurposed).

## 5 — Conflict handling (never average, never guess)

- **Detection**: two `GeometryAspect`s for the same `(aspect, locus)` from different fragments, values outside per-aspect equality tolerance (tolerances must themselves be evidence-derived — drawing precision, e.g. dimension text round-off — not invented; until derivable, exact-match + `corroboration_conflict` on any difference, which is conservative in the same direction as Phase 12.4's v1 rule).
- **Resolution order**: (1) authority rank — a corroborating source never overrides an authoritative one; its disagreement is recorded as `corroboration_conflict` evidence and *lowers* the composition's confidence (Phase 9.3 precedent: outliers reported, never averaged away). (2) Between two authoritative sources: revision block wins (A16) **when revision data exists** — Apollo is all Rev 0, so this path is designed but untested (RQ-4). (3) Otherwise: `GeometryConflict`, composition → REVIEW, human decides. There is no (4).
- **Diameter conflicts specifically**: already half-solved — Phase 12.3 emits `cross_section_diameter_corroboration`-class evidence; composition consumes the resolved identity's claims and only ever *adds* section-scale corroboration, never a second diameter source.

## 6 — Centerline assembly (the algorithm, as verifiable steps)

Input: one `PhysicalIdentity` (Phase 12, ACCEPTED) + its `GeometryFragment`s. Output: one `BarPath` + `GeometryComposition`.

1. **Select the spine**: the fragment whose `view_authority` includes `xy_path`, highest `recovery_confidence`; its `recovered_path.points` become the working centerline *in its own drawing frame* (fragments are never registered into a shared frame — A12; the composed bar's frame IS the spine's frame plus evidence-based Z).
   - Zero spine candidates → no bar; composition records `authority_absent_fallback` refused (a schedule-only identity yields *no geometry*, correctly).
   - Two spine candidates (two plans) → conflict path (§9, "multiple plans"), REVIEW.
2. **Bends**: keep the spine's own vertices as bends (existing behavior); attach `bend_radius` aspects from detail fragments *by locus* (`bend_n` counted along the spine from its start; locus mapping requires the detail callout's anchor — unresolvable locus ⇒ aspect held un-attached in the composition, never guessed onto a bend).
3. **Hooks**: for each hook aspect (detail-sourced), attach `BarHook(end=locus, ...)` at `start`/`end`. Hook length *extends* the centerline endpoint along the hook geometry (angle + length from the aspect) — this is added geometry with full provenance, not invented: every added point traces to the detail fragment.
4. **Splices/laps**: not centerline mutations — represented as annotations on the composed bar (locus + length), because a lap is two bars overlapping, and *bar multiplicity is Phase 12's jurisdiction*: if a lap means two physical bars, that's two identities (an identity-resolution finding fed BACK as a research flag, not silently handled in geometry — RQ-2).
5. **Continuity breaks**: where evidence says the bar continues beyond the drawn extent ("continues into P4", typical-notes), the centerline **ends at the drawn evidence** and the bar carries a `continuity` marker at that locus (`terminated_by_evidence=False`). The path is never extrapolated.
6. **Z placement**: from section/elevation aspects when present (`placement_source='section_evidence'`); else the existing layer heuristic, explicitly labeled and confidence-capped.
7. **Reconciliation pass**: schedule cut-length vs composed length via bend/hook allowance model — match ⇒ `corroboration_match` (confidence up); mismatch ⇒ conflict evidence (never a geometry edit). The allowance model itself (bend deduction rules) is code-of-practice knowledge — **RQ-1**, not to be hardcoded from memory.
8. **Determinism**: fragments sorted by UUID; every selection rule total-ordered; same inputs in any order ⇒ identical composition (acceptance criterion §10).

## 7 — Bends, hooks, splices, laps, continuity — representation summary

Covered in §6; the representational decisions in one place: **bends** = existing `BarBend` on the spine's vertices, radius only ever from evidence; **hooks** = existing `BarHook` + provenance-tracked endpoint extension; **splices/laps** = bar-level annotations with locus+length, never path mutations, multiplicity questions escalate to Phase 12; **continuity breaks** = terminus markers, never extrapolation.

## 8 — Phase 12 / Phase 14 boundary

Phase 12 answers *which observations are one bar* (identity). Phase 14 answers *what that bar's geometry is* (composition). Hard rules: composition consumes only ACCEPTED `PhysicalIdentity`s; it never adds/removes observations from an identity; a compositional discovery that suggests identity was wrong (e.g. two spine fragments that cannot be one bar) is **fed back as a REVIEW flag on the identity, never resolved locally**. The import-boundary test discipline from 12.4 applies in reverse: the composition module must not import hypothesis/evidence/resolver machinery — only their output types.

## 9 — Failure modes

| Failure | Detectability | Evidence | Confidence effect | Human review? |
|---|---|---|---|---|
| Conflicting hooks (two details, same end, different angles) | High — two hook aspects, same locus | Both `CompositionEvidence` trails + callout provenance | Composition → REVIEW | Yes, always |
| Different diameters across views | High — already Phase 12.3's corroboration machinery | `corroboration_conflict` | Lowers composed confidence; never blocks (diameter is identity-level) | If identity was ACCEPTED on it: yes |
| Incompatible schedule (cut length ≠ composed length beyond allowance model) | Medium — needs RQ-1 allowance model; until then, report raw delta without judgment | Reconciliation-pass evidence | Recorded; no geometry change | Yes above tolerance |
| Multiple plans (two spine candidates) | High — two `xy_path`-authoritative fragments | Both spines kept in composition | REVIEW; no bar emitted | Yes |
| Revision mismatch between sheets | Low today — revision parsing unimplemented (A16) | Revision-block fields, once parsed | Tie-break stated, not applied | Yes until RQ-4 lands |
| Missing section (no Z evidence) | High — absence of `z_placement` aspects | `authority_absent_fallback` | `placement_source='heuristic_layer_stack'`, confidence capped | No (flagged, not blocking) |
| Ambiguous detail (callout locus unparseable) | High — hook aspect with unresolved locus | Held un-attached in composition | Aspect visible but unapplied | Yes to attach |
| Fragment from a REVIEW-status identity | Structural — composition refuses input | — | No composition occurs | Identity review first |
| Spine is `fallback_straight` (recovery already degraded) | High — existing `recovery_method` | Inherited recovery provenance | Composed confidence inherits the 0.5 cap | Flagged |

## 10 — Acceptance criteria (defined before any implementation)

1. **Order-independence**: identical composition for any input ordering of fragments/drawings (hash-compared, same standard as every determinism test since Phase 7).
2. **Determinism** across repeated runs (byte-identical composition records).
3. **Explainability**: every composed segment, hook, bend, and placement answers "which drawing, which entity, which rule" via `aspect_provenance` → `GeometryAspect.source_entity_uuids` — no orphan geometry.
4. **No invented geometry**: every centerline point traces to a recovered path or an evidence-backed hook extension; the only permitted non-evidence value is the explicitly-labeled Z fallback, confidence-capped, `placement_source` visible in the viewer property panel.
5. **Conflict conservatism**: zero conflicts silently resolved; every `GeometryConflict` reaches a human-visible surface (benchmark failure bucket and/or viewer).
6. **Boundary**: composition never mutates identities (tested via the 12.4-style AST import guardrail plus output-equality checks on Phase 12 artifacts).
7. **Benchmark-measurable**: composed geometry scored against corpus `geometry.json` ground truth (hook presence/angle, shape, approximate length) — **which requires labeled geometric ground truth first**. Implementation is gated on the corpus carrying enough `geometry.json` truth to detect a regression; today's Apollo draft has 3 sketch-level entries, which is not enough. This is the Phase 13.2 gate doing its job.
8. **Existing regressions untouched**: Phase 10 single-drawing reconstruction outputs remain byte-identical (composition is additive).

## 11 — Research questions (recorded, not implemented)

- **RQ-1 — Bend/hook allowance model**: reconciling schedule cut-length with composed length needs code-of-practice deduction rules (hook allowances, bend deductions per diameter). Must come from the applicable standard/engineer confirmation, not from memory or inference. Until then the reconciliation pass reports raw deltas without judgment.
- **RQ-2 — Lap semantics vs identity**: is a lapped continuation one physical bar or two? Determines whether laps live in Phase 12 (two identities + relation) or Phase 14 (one bar + lap annotation). Engineer input required; affects the data model at §4's `GeometryConflict`/annotation boundary. No Apollo evidence either way (no lap annotations found in raw text).
- **RQ-3 — Cross-element continuity**: "continues into P4"-style facts name another element; composing across elements crosses the `drawing_number` scope boundary that Phase 12 deliberately enforces. Needs its own identity-scoping design before geometry can follow.
- **RQ-4 — Revision parsing**: A16's tie-break needs title-block revision extraction; unbuilt, and untestable on Apollo (all Rev 0). Blocked on corpus packages with real revision history.
- **RQ-5 — REVIEW-composition output policy**: should a REVIEW-status composition emit a visibly-flagged draft bar (useful in the viewer) or no bar at all (purer)? Affects viewer UX more than correctness; decide at implementation time with the viewer's QA workspace in mind.
- **RQ-6 — Equality tolerances**: per-aspect conflict tolerances should derive from drawing precision evidence (dimension round-off, drawn-symbol size). Until derivable, exact-match conservatism applies; deriving them is itself a corpus-measurement task.

---

**Summary verdict of this research**: the pieces are unusually ready — `BarPath` already carries per-path provenance, Phase 12 already delivers resolved identities with per-fact claims, and the authority matrix already exists in `engineering_assumptions.md`. What Phase 14 adds is one genuinely new mechanism (aspect-wise selection with conflict records) and one honest replacement (evidence-based Z over the invented layer stack). The single hard prerequisite is not code at all: geometric ground truth in the corpus, without which acceptance criterion #7 — the only one that can prove the engine composes *correctly* rather than just *deterministically* — cannot be evaluated. The Phase 13.2 data-collection gate therefore still binds.
