# Cross-View Fusion — Research Report (pre-implementation)

**No code was written for this task. No architecture was modified.** Per instruction, this is engineering analysis and architecture design only.

## Core thesis, stated plainly

A plan, a section, and a detail of the same panel are not three separate pieces of steel — they are three drawings of **one physical rebar**. Today the pipeline has no way to know that. Each drawing runs through Phases 1-10 in isolation and produces its own, disconnected `EngineeringFamily` objects; nothing ever checks whether `N7` on the plan and `N7` in the schedule and the hook sketch on the detail sheet are describing the same steel object. **That correlation has to be established first, deliberately, as its own step — before any geometric reconstruction of a fused bar is possible.** You cannot merge geometry from two drawings you haven't yet confirmed are talking about the same bar; doing that would just as easily fuse two *different* bars that happen to share a mark or sit near each other. This is why the model below (`PhysicalObservation` → `ObservationEdge` → `PhysicalIdentity`) exists as a distinct stage: correlate first (decide "these drawings are all the same rebar"), design/reconstruct second (only once that's decided, combine what each drawing contributes — position from the plan, diameter from the schedule, hook shape from the detail — into one real bar). Getting the order right is the entire point of the reframe in the addendum below.

## Method note, stated upfront

Of the 13 files in `test_project/`, exactly **one is machine-readable by anything available in this environment**: `SS-GF-01(M).dxf`. The other 12 are `.dwg` (8 files, real AutoCAD 2010-2012 binary, 170KB-550KB each — genuine drawings, not placeholders) and `.pdf` (4 files). I confirmed, rather than assumed, that DWG is unreadable here: no `ODAFileConverter`/`libredwg`/`dwg2dxf` is installed, the legacy `cad_reader.py::_read_dwg()` requires commercial `aspose.cad` which isn't installed, and raw `strings` extraction on the DWG binary yields nothing usable (2010+ DWG uses compressed streams). I *did* find a working path for the PDFs — macOS's built-in `qlmanage -t` rasterizes them at full resolution — and used it to actually look at 3 of the 4 PDFs (`PW-GF-09(R)/(M1)/(M2).pdf`) as a structural engineer would, not guess from filenames.

So the evidence base for this report is: **full programmatic access to `SS-GF-01(M).dxf`** (geometry, every text/mtext string, every layer, every dimension) plus **direct visual inspection of the three `PW-GF-09` PDF sheets**, plus **inference by analogy** for the 8 still-unreadable `.dwg` files, clearly labeled as such wherever used. This is a real, meaningfully different evidence base than "read the filenames and guess" — and it produced a finding that changes how several already-frozen phases' output should be understood (Step 1, below).

---

## Step 1 — What each drawing actually represents

### Directly observed: `PW-GF-09(R).pdf`, `PW-GF-09(M1).pdf`, `PW-GF-09(M2).pdf`

All three are sheets from **ES Structural Consultant** for contractor **VME Precast Products**, project "Apollo Girls Hostel Building (Right Wing) — Chittoor", element `PW-GF-09` (a precast wall panel, Ground Floor). They are not three independent drawings of three different things — they are **one drawing set, three sheets, each answering a different question about the same physical panel**:

| Sheet | Title | Answers | Key vocabulary |
|---|---|---|---|
| `(R)` | "PW-GF-09-REINF DRAWING" | *What steel is inside this panel, and in what shape?* | Elevation + 4 sections, all reinforcement drawn with **self-decoding bar marks**: `T8 UBAR @150mm`, `T8 Vertical @150mm`, `T8 Horizontal @150mm`, `T8 Ties @100mm`, `1-T12`, `2-T16`, `2-T12-Crack Bar`, `T8 Hook @100mm`. A Summary Schedule table totals bar length/weight by diameter (8/10/12/16mm, 373.57kg total). **Explicitly typical**: a note states "REINFORCEMENT TYPICAL FOR: PW-GF-09, PW-1F-09, PW-2F-09, ... PW-7F-09" — one reinforcement cage *pattern* reused across 8 physical panel instances on 8 different floors. |
| `(M1)` | "PW-GF-09-MOULD DRAWING" (sheet 1 of 2) | *What is the panel's physical shape, and where does it sit in the building?* | Elevation with dimension chains for LENGTH/NOTCH/OPENING/GEOMETRY/RECESS/CORBEL, erection-mark symbols (△1, △2), a Section 1 showing the panel's story height tied to **absolute building levels**: `100274 / GF` to `103224 / 1F SSL`. **Zero rebar bar marks appear on this sheet.** |
| `(M2)` | "PW-GF-09-MOULD DRAWING" (sheet 2 of 2) | *What embeds/dowels/lifting hardware does this specific panel need, and how much does it weigh?* | Sections 2-5, a 3D isometric sketch, a Notch Detail, a **Dowel Bar Schedule** (`N7`→16mm×6, `N8`→16mm×9) and an **Insert Schedule** (`N1`→lifting insert type `RR-SA-4.0-240`×2, `N2`→`RR-SA-2.5-150`×4, `N4`→50mm sleeve×6, `N5`→20mm sleeve×4, `N10`→wire loop×12), and a Weight Schedule (1.52m³, 3789.17kg). |

**The critical cross-referencing mechanism, observed directly**: `(M1)`'s elevation has dimension-chain rows literally labeled `N1/N2`, `N7`, `N8`, `N5`, `N4/SHEAR KEY` — these are the *same* codes as `(M2)`'s schedule tables. `(M1)` answers "where is `N7` located on the panel"; `(M2)` answers "what *is* `N7`" (a 16mm dowel bar, 6 of them). Neither sheet alone is sufficient — you need both to know that there are six 16mm dowel bars at these specific positions. **This is a real, working, human-readable instance of exactly the fusion problem this task is about**, and it gave me a concrete vocabulary (position-sheet + identity-sheet, joined by a reference code) to design against instead of an abstract one.

### Directly observed: `SS-GF-01(M).dxf` (re-examined with this new context)

This is the drawing the entire Phase 1-11 pipeline has been running against all session. Re-reading it with the `PW-GF-09` vocabulary in hand changed my understanding of it:

- Its **entire text/mtext vocabulary is 14 strings**, and it contains **zero self-decoding bar marks** (no `T8`, `T12`, `T16` pattern anywhere) — but it does contain, verbatim: `LENGTH`, `UPSTAND`, `N1/N2`, `N4`, `N6`, `N7`, repeated as 4 near-identical dimension-chain groups (at x≈68684, 78643, 84345, 90128), plus a level reference (`100224` / `GF SSL`) and an element identifier (`SS-GF-01`, on layer `A-FLOR-IDEN`).
- This is structurally the *same pattern* as `PW-GF-09(M1)`'s dimension-chain rows (`LENGTH`/`NOTCH`/`OPENING`/.../`N1/N2`/`N7`/`N8`/`N5`/`N4-SHEAR KEY`) — a **Mould-drawing-style position-reference sheet**, not a reinforcement-schedule sheet. The `(M)` suffix is very likely the same "Mould" designation as `PW-GF-09(M1)`/`(M2)`.
- I rendered the actual `S-RBAR`-layer geometry near one of the four label groups (region around x≈90128,y≈5000) and it visually confirms this: a small U-shaped bar cross-section — a horizontal base + vertical projecting legs — sitting directly under a `LENGTH`/`UPSTAND`/`N7`/`N6` label group. This is a real, physically plausible "upstand" (a short vertical concrete lip/kerb) reinforcement detail, drawn four times at four positions along the panel.
- **Consequence for this session's earlier work**: Phase 8/9 (frozen, `docs/audits/phase09/`) associated marks `N4`, `N6`, `N7` with nearby `S-RBAR` geometry and built `EngineeringFamily` objects named `N4`/`N6`/`N7`, correctly leaving their diameter unresolved (`diameter_source: missing_visual_fallback`, confidence 0.0 — see `docs/audits/phase10/10.1_geometry_recovery_redesign.md`). **This was not a bug.** `N4`/`N6`/`N7` are reference codes, not self-decoding bar marks; unlike `T12`, their diameter genuinely isn't written anywhere on this sheet. The pipeline's honest "I don't know the diameter" was the *correct* answer given the information actually present in `SS-GF-01(M).dxf` — the missing diameter almost certainly lives on `SS-GF-01(R).dwg`, the reinforcement companion sheet this pipeline has never been able to read. This reframes "N6/N7 have no diameter" from a Phase 9/10 shortcoming into **the single clearest, most concrete example of why cross-view fusion is needed** — it is not a hypothetical problem, it is the exact problem already visible in the one drawing this project has fully processed.

### Inferred by analogy, not directly observed: `PW-GF-02(R)/(M1)/(M2)`, `SS-GF-01(R)`, `PW-GF-09` `.dwg` duplicates of the PDFs

I cannot read these. But `PW-GF-02(R)/(M1)/(M2)` share the exact same naming convention as the fully-decoded `PW-GF-09` set, so by structural analogy (not direct evidence) I'd expect the same R/M1/M2 split: `PW-GF-02(R)` = typical reinforcement cage (T-marks) shared across a `PW-*-02` panel family; `PW-GF-02(M1)`/`(M2)` = this specific panel instance's mould geometry, levels, embeds, and schedules. `SS-GF-01(R).dwg` — by the same analogy — is very likely the reinforcement companion to `SS-GF-01(M).dxf`, and is almost certainly where `N4`/`N6`/`N7`'s actual diameters are defined. I want to be explicit that this is inference, flagged as such, not something I verified — the honest-uncertainty standard this project has held throughout applies here too.

### `identity_parser.py`'s current blind spot

`core/identity_parser.py::parse_identity()` extracts `view` (e.g. `"M"`, `"R"`, `"M1"`, `"M2"`) as an **opaque string with no semantic meaning anywhere in the codebase** — confirmed by reading the parser and grepping for any consumer of `.view`. The pipeline currently has zero concept that `"R"` means "this sheet has the authoritative bar marks" or that `"M"` means "this sheet has positions and levels but not diameters." That semantic gap is exactly where fusion needs to attach.

---

## Step 2 — Where fusion belongs in the existing architecture

Current pipeline (frozen, `docs/README.md`):
```
Phase 1  Project Manager        -- discovers drawings, parses filename identity (drawing_number/floor/element/VIEW)
Phase 2  Geometry Import        -- per-drawing, DXF -> typed entities
Phase 3  Canonicalization       -- per-drawing
Phase 4  Spatial Index          -- per-drawing
Phase 5  Canonical Nodes        -- per-drawing
Phase 6  Connectivity Graph     -- per-drawing
Phase 7  Recognition            -- per-drawing, per-component shape classification
Phase 8  Engineering Association -- per-drawing, annotation-to-geometry (marks, diameter, spacing)
Phase 9  Engineering Families   -- per-drawing, groups same-mark bars into families
Phase 10 Physical Reconstruction -- per-drawing, families -> centerlines -> meshes
```

**Every phase from 2 through 10 operates on exactly one drawing at a time**, and nothing in `core/full_pipeline.py::run_pipeline_through_phase9()` (or any earlier phase) ever looks at a second drawing. `DrawingProject.load_directory()` (Phase 1) *does* discover all drawings in a project and already builds a `Project -> Floor -> Element -> DrawingSet -> Drawing` relationship graph (`core/project.py::_build_relationships`) — this is the one piece of the existing architecture that already groups `SS-GF-01(M)` and `SS-GF-01(R)` together as members of the same `DrawingSet` (`SS-GF-01`). **Fusion has a real anchor point to build on: Phase 1 already knows which drawings belong together, it just never uses that grouping for anything downstream.**

The natural seam is **after Phase 9 (families exist, per drawing) and before/alongside Phase 10 (reconstruction, which currently assumes one drawing's families are the complete picture)**. Concretely:
```
Phase 9   (frozen, unchanged)  -- per-drawing families, as today
Phase 11  Cross-View Fusion (NEW) -- takes N drawings' Phase 9 output (already grouped by
                                      Phase 1's DrawingSet), produces fused families with
                                      resolved diameter/spacing/mark identity + provenance
                                      back to which drawing contributed which fact
Phase 12  Physical Reconstruction -- unchanged logic, but now consumes fused families
                                      instead of one drawing's families
```
Phase 11 is a numbering collision with the already-frozen viewer work (`docs/audits/phase11/`), addressed in Step 7.

---

## Step 3 — How a human engineer actually does this

Watching how the `PW-GF-09` set cross-references itself gives a concrete answer, not a generic one:

1. **Read the `(R)` sheet first, build a mental bar-mark dictionary.** `T8 UBAR @150mm`, `1-T12`, etc. — these are self-contained; no other sheet is needed to know what a `T`-mark *is*. The engineer now knows the panel's reinforcement *pattern*, in isolation from any specific building position.
2. **Read the `(M)` sheet(s) to find out where the panel actually sits and what non-reinforcement hardware it needs.** Absolute levels (`100274/GF` → `103224/1F SSL`) place this specific instance in the building. Reference codes (`N1`, `N7`...) point to a *different* namespace than the `(R)` sheet's `T`-marks — the engineer does not confuse `N7` (a dowel, resolved via the `(M2)` schedule) with a `T`-mark bar.
3. **Match same-shape, same-mark elements across sheets by mark identity first, position second.** If `(R)` says "typical for PW-GF-09...PW-7F-09," the engineer knows the *same* `T`-mark dictionary applies to 8 different physical instances without re-deriving it 8 times — they translate each instance's *position* (from that instance's own `(M)` sheet) while reusing the *shape* (from the one shared `(R)` sheet).
4. **Treat unresolvable references as open questions, not guesses.** If `N4`/`N6`/`N7` appeared on a Mould sheet with no matching schedule anywhere in the set, a competent engineer would flag it for RFI (request for information), not silently invent a diameter. This is precisely the discipline this pipeline has already been built with (Phase 7.6 plausibility, Phase 10.1 diameter provenance) — human and machine reasoning converge on the same principle: **absence of information is a fact to report, not a gap to paper over.**
5. **Reconcile conflicts by trusting the more specific/more recent source, but never silently.** A revision block (visible on every sheet's title block: `Rev / Date / Description / Chkd / Appd`) is the authoritative tie-breaker when two sheets disagree — an engineer checks revision numbers, not just content, before deciding which value wins.

---

## Step 4 — Proposed data model

Grounded in the `T`-mark/`N`-mark distinction actually observed (Step 1), the model needs to separate **identity resolution** (what is this bar, unambiguously) from **spatial placement** (where is it, in this specific instance) from **the evidence trail** (why do we believe this):

```python
@dataclass
class DrawingRole:
    """What Step 1 established a drawing IS, not just its filename suffix.
    Populated by classifying each drawing (see Step 6), not assumed from
    the 'view' string -- identity_parser.py's 'view' field is the input
    evidence to this classification, not the classification itself."""
    role: str  # 'reinforcement_typical' | 'mould_instance' | 'schedule' | 'unclassified'
    confidence: float
    evidence: List[str]  # e.g. "contains self-decoding T-mark pattern", "contains absolute level references"


@dataclass
class MarkNamespace:
    """T8/T12/T16-style marks and N1/N7-style marks are NOT the same
    namespace and must never be matched against each other. This makes
    that distinction a first-class, explicit fact instead of an
    implicit assumption buried in a regex."""
    prefix_pattern: str          # e.g. r'^T\d{1,2}$' vs r'^N\d{1,2}(/N\d{1,2})?$'
    self_decoding: bool          # True for T-marks (diameter IS the mark); False for N-marks
    source_drawing_role: str     # which DrawingRole this namespace's marks are typically defined on


@dataclass
class FusionEvidence:
    rule: str                    # e.g. "mark_identity_match", "typical_note_match", "position_proximity"
    score: float
    explanation: str
    source_drawing: str          # which drawing contributed this evidence
    source_uuid: Optional[UUID]  # the specific annotation/component/text entity, if applicable


@dataclass
class FusionCandidate:
    """One proposed link between an object in drawing A and an object in
    drawing B, BEFORE it's accepted -- mirrors AssociationCandidate's
    existing accept/reject-with-evidence pattern from Phase 8, applied one
    level up (across drawings instead of within one)."""
    object_a: UUID
    drawing_a: str
    object_b: UUID
    drawing_b: str
    relationship: str            # 'same_mark_different_instance' | 'position_identity_pair' |
                                  # 'typical_pattern_reference' | 'conflicting_revision'
    evidence: List[FusionEvidence]
    combined_score: float


@dataclass
class CrossViewBar:
    """A bar whose full identity required >1 drawing to resolve --
    NOT a replacement for EngineeringFamily, a wrapper that RECORDS how
    many drawings contributed and what each one contributed, so the
    provenance chain (Phase 11.3's stated goal) extends across drawings
    instead of stopping at one."""
    uuid: UUID
    mark: str
    diameter: Optional[float]
    diameter_source_drawing: Optional[str]   # e.g. "PW-GF-09(R)"  -- may differ from the
                                              # drawing the geometry/position came from
    spacing: Optional[float]
    spacing_source_drawing: Optional[str]
    position_source_drawing: str             # e.g. "PW-GF-09(M1)" -- where this instance sits
    contributing_families: Dict[str, UUID]   # drawing_filename -> EngineeringFamily.uuid, one
                                              # per drawing that contributed a fact
    fusion_confidence: float                 # independent of any single drawing's engineering
                                              # confidence (Phase 9.4 pattern, one level up)
    unresolved_fields: List[str]             # e.g. ["diameter"] if no drawing in the set
                                              # ever provided it -- explicit, not silently None


@dataclass
class DrawingAlignment:
    """How drawing B's coordinate system maps onto drawing A's, when they
    need to agree on WHERE something is (e.g. a plan and a section of the
    same panel). Distinct from CrossViewBar's position_source_drawing,
    which just records provenance, not a transform."""
    drawing_a: str
    drawing_b: str
    transform: Optional[Any]     # translation/rotation/mirror, or None if unknown
    confidence: float
    evidence: List[FusionEvidence]


@dataclass
class CrossViewAssembly:
    """The fused equivalent of ReinforcementAssembly -- an assembly built
    from CrossViewBars instead of PhysicalBars, still per building
    element (e.g. one SS-GF-01 assembly, one per PW-*-09 panel instance),
    not one global assembly for the whole project."""
    uuid: UUID
    element_id: str              # from Phase 1's DrawingIdentity, e.g. "SS-GF-01"
    bars: List[CrossViewBar]
    source_drawings: List[str]
    qa: 'CrossViewQA'


@dataclass
class CrossViewQA:
    conflicts: List[FusionCandidate]       # candidates that scored ambiguously, not auto-resolved
    unresolved_marks: List[str]            # marks with no cross-drawing resolution found at all
    missing_companion_drawings: List[str]  # e.g. "SS-GF-01(R)" expected but unreadable/absent
```

Two deliberate design choices, both directly evidence-driven:
- **`MarkNamespace` exists because the evidence demands it.** Treating `T12` and `N7` as the same kind of thing (both matched by one `MARK_PATTERN` regex, as `AnnotationParser` currently does) is exactly the ambiguity that a fusion engine must not inherit — fusion must know it should never try to "resolve" `N7`'s diameter by looking for a matching `T7` somewhere.
- **`unresolved_fields` is not an afterthought.** Given that `SS-GF-01(M)`'s `N6`/`N7` are very likely never resolvable without `SS-GF-01(R)` (a file this pipeline may never be able to read, per Step 9), the data model must make "this project cannot resolve X" a first-class, queryable, honestly-reported state — not a `None` that looks the same as "not yet computed."

---

## Step 5 — Evidence, confidence, failure modes per fusion decision

Following the `FusionCandidate`/`FusionEvidence` shape above, every fusion decision must be able to answer:

| Decision type | Evidence | Confidence factors | Failure modes | Conflict handling |
|---|---|---|---|---|
| **Same mark, different drawing instance** (e.g. `PW-GF-09`'s `T8 UBAR` pattern applies to `PW-1F-09` too, per the "typical for" note) | Exact mark-string match + explicit "typical for" note text match | 1.0 if the typical-note lists the target drawing by name; lower if only inferred from naming-pattern similarity | Two different consultants' drawings could reuse mark `N4` for *different* things (marks are not globally unique, only unique within one drawing set) — must scope every mark match to the DrawingSet, never globally | If two `(R)` sheets both claim to be "typical for" the same instance, flag as a conflict, do not silently pick one |
| **Position + identity pair** (`(M1)`'s `N7` position + `(M2)`'s `N7` schedule entry) | Reference-code exact string match, both drawings in the same DrawingSet | High if the code appears in both a dimension-chain row (position sheet) and a schedule table (identity sheet) — the *dual appearance* itself is strong evidence, not just the string match | A code like `N1/N2` (compound reference) needs to split into two separate lookups, not one — get this wrong and one dowel's data silently overwrites the other's | If the schedule has no entry for a position-sheet's code (as observed: no schedule for `SS-GF-01(M)`'s `N4`/`N6`/`N7` exists in the set at all), report `unresolved_fields`, do not fabricate |
| **Typical-pattern reference** (one `(R)` sheet supplying diameter/spacing to 8 mould instances) | The `(R)` sheet's own "typical for" note, cross-checked against Phase 1's `DrawingSet`/`element` grouping | High only if Phase 1's `element` field for each mould instance matches an entry in the typical-note's list, verified, not assumed from filename similarity alone | The typical note could be stale (drawing revised, note not updated) — this is a real risk category (Step 9), not hypothetical, since revision blocks exist precisely because sheets get revised independently | Prefer the higher revision number's content when the same mark appears with different values across revisions of the "same" sheet |
| **Conflicting geometry** (two drawings disagree on a dimension for what should be the same feature) | Numeric comparison with tolerance, tagged with both source drawings | Confidence *drops*, does not average, when sources disagree beyond tolerance — matches this project's established pattern (Phase 9.3: an outlier gap was reported as an anomaly, never silently averaged away) | Mirrored/rotated sections could make "the same dimension" appear as two *different but both-correct* numbers if the transform (`DrawingAlignment`) is wrong or missing | Always surface the raw conflict in `CrossViewQA.conflicts`; never resolve by averaging, majority vote, or "most recent wins" without an explicit, logged reason |

---

## Step 6 — Information required for fusion

Directly identified as necessary from the evidence in Step 1, not a generic checklist:

1. **Mark/reference-code text**, already extracted by `AnnotationParser` (Phase 8) — but needs the `MarkNamespace` split (Step 4) to distinguish self-decoding (`T`) from lookup-required (`N`) codes, which the current single `MARK_PATTERN` regex does not do.
2. **"Typical for" / scope notes** — plain text, currently not parsed at all (`AnnotationParser` has no pattern for this). This is a real, observed gap: the exact sentence that tells you 8 drawings share one reinforcement pattern is sitting in the DXF/PDF as ordinary text and nothing in the pipeline looks for it.
3. **Schedule tables** (Dowel Bar Schedule, Insert Schedule, Weight Schedule, Summary Schedule) — structured tabular data, currently **entirely unhandled**. `core/recognition/annotations.py` has no concept of a table; these are presumably `INSERT`/`HATCH`/multiple-`TEXT` clusters in the DXF that the current pipeline would either ignore or (worse) misparse as scattered unrelated annotations.
4. **Absolute level references** (`100274/GF`, `103224/1F SSL`) — needed to know *which* physical instance of a repeated element a given Mould sheet describes; not currently extracted or used anywhere.
5. **Revision block content** (`Rev / Date / Description / Chkd / Appd`) — needed for the conflict tie-breaking rule in Step 5; not currently extracted.
6. **Drawing-set membership**, already available from Phase 1 (`core/project.py::_build_relationships`) — the one piece of this list already implemented, just not consumed downstream.
7. **Coordinate alignment** between a plan/elevation and its sections — needed for `DrawingAlignment`; not currently computed, and per Step 9, may not always be geometrically derivable (a section is often drawn at an arbitrary, unrelated sheet location, not literally cut-and-placed at true position, as seen in `PW-GF-09(M1)`'s "SECTION 1" sitting in blank space to the right of the elevation, not aligned to it in DXF space at all).

---

## Step 7 — Pipeline integration: new phase, not a replacement

**Recommendation: a new phase, numbered Phase 12** (not Phase 11 — that number is already used and frozen for the viewer, `docs/audits/phase11/`; not a replacement of Phase 9 or 10). **Renamed in Addendum 2 below from "Cross-View Fusion" to "Phase 12 — Physical Identity Resolution"** — the scope is unchanged, the name was corrected to say what the phase actually resolves (identity) rather than what it superficially looks like it's doing (combining drawings).

Justification:
- **Not part of Phase 9.** Phase 9 (Engineering Families) is frozen, regression-locked, and correct *for what it's scoped to do*: build families from one drawing's own annotations. Extending it to reach into other drawings would break its single-drawing determinism guarantee (`tests/determinism.py`) and conflate two genuinely different concerns — "what does this drawing say" vs. "what do all the drawings, together, say." Every phase boundary in this project so far has separated concerns exactly this cleanly (geometry vs. recognition vs. association vs. reconstruction); fusion deserves the same treatment, not a bolt-on.
- **Not part of Phase 10.** Reconstruction should consume *already-fused* families, the same way it currently consumes already-built ones — Phase 10's job (geometry recovery, tube sweep, mesh generation) is orthogonal to *which* families it's handed. Making Phase 10 fusion-aware would re-couple two things this session went to real effort to decouple (`core/full_pipeline.py`'s whole point, Phase 11.1).
- **A new phase, because fusion is genuinely a new kind of operation** — every phase 2-10 processes one drawing; this is the first phase whose *input* is inherently plural. It deserves its own audit trail (`docs/audits/phase12/`), its own determinism test (comparing fused output across repeated runs, same standard as every other phase), and its own freeze criteria, rather than being smuggled into an existing phase's scope.
- **Numbered 12, not 11**, purely because 11 is taken. If this is confusing later, renumber the viewer work retroactively rather than have two different things claim "Phase 11" — but that's a documentation housekeeping decision, not an architectural one, and out of scope for this research task.

---

## Step 8 — Three fusion strategies, compared

**Strategy A — Geometry-first.** Align drawings spatially (shared coordinate origin, or a computed `DrawingAlignment`), then match objects that overlap in aligned space, using annotation text as a secondary signal only.
**Strategy B — Annotation-first.** Match objects purely by mark/reference-code text equality within a `DrawingSet` (as observed working in the `PW-GF-09` `(M1)`↔`(M2)` example), using geometry only as a tie-breaker among same-mark candidates.
**Strategy C — Evidence graph.** Build a graph of `FusionCandidate` edges from *every* available signal (mark text, typical-notes, schedule membership, geometry proximity, level references) simultaneously, and resolve via a scoring/voting pass rather than a fixed pipeline order — the natural generalization of `FusionEvidence`/`FusionCandidate` from Step 4/5.

| | Robustness | Engineering correctness | Scalability | Implementation complexity | Explainability |
|---|---|---|---|---|---|
| **A: Geometry-first** | Low — the one concrete example observed (`PW-GF-09(M1)`'s Section 1 sitting in unrelated blank space, not spatially aligned to the elevation it describes) directly contradicts the assumption this strategy depends on | Poor — an engineer does not primarily think in shared coordinates across sheets; mark identity is the actual reasoning tool (Step 3) | Poor — requires solving a nontrivial alignment problem (rotation/mirroring/arbitrary sheet placement) before any matching can happen at all | High — full 2D/3D registration, handling mirrored/rotated views | Poor — "these overlap in space" is a weak, unintuitive explanation for why two objects are "the same bar" |
| **B: Annotation-first** | Good for the exact case observed (`(M1)`↔`(M2)` via `N7`), but fragile for the `N4`/`N6`/`N7`-with-no-schedule case — has nothing to fall back on when the matching annotation genuinely doesn't exist in the set | Good — matches the human reasoning process from Step 3 directly | Good — text matching scales trivially; no geometric computation required | Low — mostly string matching plus the `MarkNamespace` scoping rule | Excellent — "matched because both say `N7`" is exactly how a human would explain it |
| **C: Evidence graph** | Best — degrades gracefully; when annotation match is unavailable (the unresolved-`N4` case), other evidence (typical-notes, drawing-set membership, position proximity as weak corroboration) still contributes a score instead of a hard failure | Best — mirrors Step 3's actual human process, which uses *multiple* signals (mark, typical-note, revision) together, not one in isolation | Good — incremental; new evidence types can be added without restructuring existing matches, same as Phase 8's `AssociationCandidate` pattern already does within one drawing | Highest — most design/testing surface area, most ways to get scoring weights wrong | Good, if `FusionEvidence` is genuinely kept per-candidate (as designed in Step 4) rather than collapsed into one opaque score — the discipline this project has held throughout (every confidence number must decompose, Phase 9.4) applies directly here |

**Recommendation: Strategy C (evidence graph), built by extending, not replacing, patterns already proven in this codebase.** `EngineeringAssociationEngine`'s candidate/evidence/threshold model (Phase 8) and the Phase 9.4 confidence-decomposition pattern are *already* a working, audited, one-drawing instance of exactly this strategy. The recommendation is to generalize a pattern that has already been built and proven, not invent a new paradigm — which also directly answers Step 7's implicit sub-question (does the current architecture already support part of fusion): **yes, its core matching philosophy does; only the "reach across drawings" part is new.**

---

## Step 9 — Biggest risks

| Risk | Observed evidence, or reasoned inference | Handling |
|---|---|---|
| **DWG unreadability blocks fusion entirely for 8 of 9 non-DXF drawings** | Directly confirmed this session (Step 1 method note) — not hypothetical | This is the actual highest-priority risk, ranked above every architectural question in this report. A perfect fusion design is useless against files the pipeline cannot open. Needs its own decision (ODA File Converter integration, a commercial SDK, or scoping the project to DXF-only inputs) before Phase 12 has anything real to fuse beyond `SS-GF-01(M)` alone. |
| **Marks are not globally unique** — `N4`/`N6`/`N7` could mean something completely different in a different consultant's drawing set | Directly observed: `PW-GF-09`'s `N4` (a 50mm sleeve) and `SS-GF-01`'s `N4` (an upstand reference) are almost certainly unrelated despite the identical code, because they come from different drawing sets/consultants | Scope every mark match strictly within one `DrawingSet` (Phase 1's existing grouping); never match marks across element boundaries |
| **"Typical for" notes can go stale** | Inferred risk, not observed going stale in this evidence set, but the mechanism (a note manually listing 8 drawing numbers) is inherently a manual, unenforced invariant | Treat typical-note matches as evidence to log and verify against revision dates, not an unconditional truth; flag when a nominally-covered drawing's own content contradicts the typical pattern |
| **Missing companion drawings** (the `SS-GF-01(M)`/`N6`/`N7` diameter case) | Directly observed and unresolved in this project's own current test data | `CrossViewQA.unresolved_marks`/`missing_companion_drawings` must be first-class, visible output — not swallowed into a lower confidence number. This is precisely what the Phase 10.1 diameter-provenance work already got right for the single-drawing case; fusion must not regress that discipline just because the problem got harder. |
| **Mirrored/rotated sections** | Not directly observed (no evidence either way in what I could read), but structurally likely given `PW-GF-09(M1)`'s Section 1 is drawn in a completely different, unrelated part of the sheet's coordinate space from the elevation it sections — sections are clearly not literal spatial subsets of the plan/elevation in this drawing convention | `DrawingAlignment.transform` must default to "unknown," never assumed identity; Strategy C's annotation-first-with-geometry-as-corroboration ordering specifically avoids depending on solving this |
| **Conflicting revisions** | Not observed (all 3 read PDFs are `Rev 0`), but the revision block exists on every sheet specifically because this happens in practice | Tie-break by revision number/date per Step 5; never by "most recent file mtime" (mtimes reflect when a file was copied/exported, not drawing revision) |
| **Duplicated bars across a fused count** | Real risk once families from multiple drawings get merged — e.g. if both `(M1)` and `(M2)` happened to reference the same physical dowel via slightly different codes, a naive fusion could double-count it in a weight/count schedule | `CrossViewBar` is one object per physical bar, with `contributing_families` recording every drawing that mentioned it — a merge, not a union followed by re-counting |

---

## Deliverables checklist (per the 9 requested items)

1. ✅ Engineering analysis of supplied drawings — Step 1, grounded in direct PDF inspection + full DXF data access, with inference-by-analogy explicitly labeled where used.
2. ✅ Understanding of existing architecture — Step 2, anchored to specific files/functions (`core/project.py::_build_relationships`, `core/full_pipeline.py`).
3. ✅ Human reasoning process — Step 3, derived from the actual observed `PW-GF-09` cross-referencing mechanism, not a generic description.
4. ✅ Proposed architecture / data model — Step 4.
5. ✅ Evidence/confidence/failure-mode framework — Step 5.
6. ✅ Required information — Step 6.
7. ✅ Pipeline integration — Step 7 (new Phase 12, justified).
8. ✅ Strategy comparison + recommendation — Step 8 (Strategy C, evidence graph).
9. ✅ Risks — Step 9, ranked, with DWG unreadability flagged as the actual top blocker.

## Phased implementation roadmap (for when implementation is authorized — not started here)

1. **Resolve DWG readability** (Step 9's top risk) — without this, Phase 12 has only one drawing (`SS-GF-01(M)`) to "fuse," which isn't a meaningful test of the architecture.
2. **Extend `AnnotationParser`** with a `MarkNamespace`-aware pattern (self-decoding vs. reference-code marks) and a "typical for" note parser — both are text-parsing extensions to Phase 8's existing `AnnotationParser`, not new architecture.
3. **Build the minimal `FusionCandidate`/`FusionEvidence` matcher** (Strategy C) scoped to the one real, fully-observed case: `(M1)`↔`(M2)` position/identity pairing via reference-code match — this is directly testable against the `PW-GF-09` set once DWG reading works, with a known-correct answer to check against (I can already state by hand what `N7` should resolve to: 16mm × 6, from the PDF).
4. **Add `CrossViewQA`/unresolved-field reporting** before attempting any "typical for" cross-instance propagation — get the honest-failure path right first, matching this project's established sequencing discipline (plausibility before optimization, throughout Phases 7-10).
5. **Only then** attempt the harder, less-evidenced cases: `DrawingAlignment` for section/elevation matching, and cross-instance "typical for" propagation across the 8 `PW-*-09` panels.

---

## Addendum — Physical Identity Reframe (revision after review)

**Still pure research. No code. No architecture modified.** This addendum revises the Step 4 data model and the geometric-alignment portion of Step 6/9 above. It does not revise Steps 1, 2, 3, or the drawing evidence in Step 1 — those hold. What was wrong is narrower and more specific: the original model made **drawings** the unit that evidence attaches to (`CrossViewBar.diameter_source_drawing`, `FusionCandidate.drawing_a`/`drawing_b`). That's metadata fusion — matching records across tables. It is not the same operation as recognizing that a plan mark, a section's drawn cross-section, and a detail's dimensioned hook sketch are three partial views of *one steel object*. The distinction matters because the second problem needs a persistent object identity that observations attach *to*, independent of any pair of drawings — the first model has no such object; it only has pairwise links between drawings.

### Answering the forced question directly

*"Forget the drawings. Assume there is a real physical rebar cage inside the concrete. Every drawing is only one observation of that cage."*

Taking this literally: the primary object is the physical bar (or, one level up, the physical cage/assembly it belongs to). It exists once, has one true geometry (a centerline, a diameter, a set of bends/hooks) and one true identity (whatever mark the engineer assigned it), regardless of how many sheets happen to depict it. A drawing never *contains* a bar — it contains marks, lines, and dimensions that are **evidence about** a bar that exists independently of the drawing. This is not a new principle for this codebase — it is the same relationship `EngineeringFamily` already has to `ComponentRecord` within one drawing (Phase 9: a family is inferred *from* components, and is not itself drawn) — the reframe is to run that same "the record is inferred, not drawn" discipline one level up, across drawings, instead of stopping at the drawing boundary.

### Revised data model

`CrossViewBar` from Step 4 is retired as the central node. In its place:

```python
@dataclass
class PhysicalObservation:
    """One drawing's contribution of evidence about SOME physical object --
    not yet claimed to belong to a specific identity. The atomic unit fusion
    operates on. Roughly one per EngineeringFamily/annotation/schedule-row
    encountered, tagged with what KIND of evidence it is."""
    uuid: UUID
    source_drawing: str
    source_family_uuid: Optional[UUID]     # link back into that drawing's own
                                            # frozen Phase 9 output, if applicable
    role: str            # 'plan_position' | 'section_cross_section' |
                          # 'detail_geometry' | 'schedule_identity' |
                          # 'elevation_position'
    mark_text: Optional[str]
    geometry: Optional[Any]                # this drawing's own local geometry,
                                            # untransformed -- fusion does not
                                            # require it to already be in a
                                            # shared frame (see below)
    numeric_facts: Dict[str, float]        # e.g. {'diameter': 16.0}, {'hook_radius': 48.0}


@dataclass
class AttachmentPoint:
    """WHERE on the physical object an observation applies. A detail sketch
    of a 90-degree hook does not describe the whole bar -- it describes one
    END of it. Without this, a hook detail has no way to say which end, or
    a mid-length bend has no way to say which bend, of a bar with several."""
    locus: str            # 'start' | 'end' | 'bend_n' | 'whole_bar'
    reference: Optional[str]  # the callout symbol/number that anchored this,
                               # e.g. detail marker "A", section marker "3"


@dataclass
class ObservationEdge:
    """Supersedes FusionCandidate for the identity-resolution step -- an
    edge between two PhysicalObservations, not between two drawings. Two
    observations from the SAME drawing can also be edges (e.g. a plan mark
    and that same drawing's own schedule row) -- identity resolution does
    not stop at drawing boundaries in either direction."""
    observation_a: UUID
    observation_b: UUID
    relationship: str     # 'mark_identity_match' | 'section_reference_match' |
                           # 'detail_callout_match' | 'schedule_lookup_match' |
                           # 'cross_section_diameter_corroboration'
    evidence: List[FusionEvidence]     # unchanged from Step 4
    combined_score: float


@dataclass
class PhysicalIdentity:
    """The resolved node. ONE per real bar (or embed/dowel). Observations
    point TO this; it does not point to drawings. Mirrors PhysicalBar's
    relationship to its constituent components (Phase 10) one level up."""
    uuid: UUID
    mark: Optional[str]
    diameter: Optional[float]
    observations: List[PhysicalObservation]        # every drawing's contribution,
                                                     # with AttachmentPoint per item
    resolution_confidence: float                    # confidence this cluster of
                                                     # observations is genuinely
                                                     # one object, not a merge error
    unresolved_fields: List[str]
    ambiguous_alternative_clusters: List[UUID]       # other PhysicalIdentity uuids
                                                      # this one was hard to
                                                      # distinguish from, if any --
                                                      # makes near-miss merges/splits
                                                      # visible instead of silent
```

`CrossViewAssembly`, `CrossViewQA`, and `FusionEvidence` from Step 4 carry over unchanged — `CrossViewAssembly.bars: List[CrossViewBar]` becomes `List[PhysicalIdentity]`.

### How identity actually propagates without a coordinate transform

This is the part the original report under-specified. The report is right that there is often no valid coordinate transform between a plan, a section, and a detail — they are different projections, sometimes drawn at different scales, and (directly observed in `PW-GF-09(M1)`) a section is frequently placed in blank sheet space unrelated to where it was cut from, not spatially registered to its parent view at all.

But the drawing set doesn't need one, because **it already solves this problem itself, symbolically, and I have direct evidence of the mechanism**: `PW-GF-09(M1)` carries numbered erection-mark symbols (△1, △2) and section-marker symbols (3, 4, 5) on the elevation; each numbered section sheet is *titled* with the matching number. `SS-GF-01(M).dxf`'s own text inventory independently contains the same pattern — bare symbol numbers `'1'`, `'2'`, `'3'` co-located with each of the four `LENGTH`/`UPSTAND`/`N`-mark groups. A human reader (and, by direct analogy, a section marker in *any* structural drawing convention) resolves "which section shows this part of the plan" not by aligning coordinates, but by **reading a number off a symbol and finding the sheet/view labeled with that number** — exactly the same reference-code-lookup mechanism already used for `N7` (position sheet) → `N7` (schedule sheet). Section/detail-callout resolution is not a distinct geometric problem needing a new mechanism; it is **the same symbolic `ObservationEdge` matching** (`relationship='section_reference_match'` / `'detail_callout_match'`), just applied to view-level callout symbols instead of bar-mark text.

Consequence: `DrawingAlignment` (Step 4) is **demoted, not deleted**. It remains useful for the narrower case where two sheets genuinely do share a coordinate system (e.g., possibly `SS-GF-01(M)`'s own four repeated upstand instances, all in one DXF's single coordinate space — confirmed directly, since I measured their positions myself: x=68684/78643/84345/90128). It is *not* the general mechanism for cross-view-type fusion (plan↔section↔detail), which is symbolic reference-resolution as described above, not spatial registration. This is a meaningful complexity reduction from the original report: no projective-geometry/registration problem needs solving at all for the identity question — only for the narrower, optional task of *placing* a resolved bar's geometry in one shared 3D frame once its identity is already known (relevant to 12.3 below).

### How geometric fusion actually produces ONE centerline (the question the original report didn't answer)

Once a `PhysicalIdentity` has a resolved cluster of observations, building its merged geometry is **not** a spatial-registration/point-cloud-merge problem (there is usually no shared frame to merge into, per above). It is a **hierarchical composition** problem: each observation role is authoritative for a specific *aspect* of the bar, and the merge picks the best-authority source per aspect rather than averaging or spatially blending everything:

| Aspect | Authoritative source | Why | Corroborating (not primary) sources |
|---|---|---|---|
| Path / centerline shape (the bulk of the bar) | `plan_position` or `elevation_position` observation with real, to-scale, single-coordinate-frame geometry (e.g. `SS-GF-01(M)`'s actual `S-RBAR` polyline — directly measured, not schematic) | This is the only source that is simultaneously *to-scale* and *in one coordinate frame* for its own extent — exactly Phase 10's existing `recovery_method` philosophy (walk real connectivity, don't synthesize from stats) applied across drawings instead of within one | `detail_geometry` observations, if their dimensions are consistent with the plan-derived path's local shape at the attachment locus |
| Diameter | Self-decoding mark text (`T12`) directly, OR `schedule_identity` observation's numeric fact, for reference-coded marks (`N7`→16mm) | Matches Step 1's finding: this is literally where the number is authoritatively defined | `section_cross_section` observation's drawn circle diameter, at true section scale — a genuine independent check, not a source of truth (flag `cross_section_diameter_corroboration` as a *mismatch* risk if it disagrees, don't silently average) |
| Hook / bend detail at one end or one bend | `detail_geometry` observation, attached via `AttachmentPoint` to the specific locus its callout symbol references | This is the one aspect a plan/section view usually can't depict at usable resolution — the reason a separate detail sheet exists at all | Plan-derived path's own local direction change at that locus, as a sanity check that the detail's implied geometry doesn't contradict the plan's drawn bend |
| Position in the building (3D placement) | Panel-local dimension chain (offset from a reference edge, per `PW-GF-09(M1)`'s dimension rows) + panel's own absolute level/erection position (Phase 1 identity + `(M1)`-style level tags) | Directly observed as the actual mechanism precast drawings use to place an otherwise schematically-drawn reference in real 3D space | — |

This table *is* the answer to "how does fusion actually happen geometrically": not a merge algorithm, a **per-aspect authority assignment**, composed once per resolved `PhysicalIdentity`. It's a deliberately narrower claim than generic multi-view geometric fusion (as in computer-vision multi-view reconstruction) — narrower because the evidence (Step 1's drawing set) shows structural precast documentation doesn't need or provide the shared-frame data that generic CV fusion assumes; it substitutes explicit symbolic cross-referencing and dimensioned text instead. Adopting the CV framing as the *mental model* (per the forced question) was the right instinct; adopting CV *registration algorithms* as the *mechanism* would have been over-engineering against evidence that isn't there.

### Revised phased roadmap (supersedes the flat 5-item list above)

| Phase | Scope | Depends on |
|---|---|---|
| **12.0 — Physical Identity Model** | Land `PhysicalObservation`, `AttachmentPoint`, `ObservationEdge`, `PhysicalIdentity` as data structures only, populated by hand/fixture for the one fully-decoded case (`PW-GF-09` `N7`: plan position + schedule identity, known-correct answer = 16mm×6) — proves the model shape before any matching logic exists | DWG readability (Step 9's top risk) for anything beyond the `PW-GF-09` PDFs already read by hand |
| **12.1 — Observation Graph** | Build `PhysicalObservation` extraction from each drawing's already-frozen Phase 8/9 output (mark text, schedule rows, "typical for" notes, section/detail callout symbols — the new parser work from Step 6) and connect them via `ObservationEdge` using the symbolic-matching rules above, scored per `FusionEvidence` | 12.0 |
| **12.2 — Identity Resolution** | Cluster the observation graph into `PhysicalIdentity` nodes (connected-components-with-threshold, or graph community detection over `combined_score`); this step owns ambiguity handling explicitly — near-threshold clusters populate `ambiguous_alternative_clusters` rather than being force-resolved, matching this project's standing rule (Phase 9.1/7.6) that low-confidence structure gets flagged, not guessed | 12.1 |
| **12.3 — Geometric Fusion** | Apply the per-aspect authority table above to each resolved `PhysicalIdentity` to produce one merged geometric description (centerline + diameter + hooks) with the corroboration checks (e.g. section-diameter mismatch) surfaced, not silently resolved | 12.2 |
| **12.4 — Reconstruction Integration** | Feed `PhysicalIdentity` objects into the **unchanged** frozen Phase 10 reconstruction pipeline in place of single-drawing families — Phase 10's tube-sweep/mesh logic doesn't need to know its input came from fusion | 12.3, and requires Phase 10's existing input contract (`EngineeringFamily`-shaped data) to be satisfied by `PhysicalIdentity`, likely via a thin adapter rather than a Phase 10 change |

This directly replaces the flat 5-item roadmap earlier in this document for planning purposes; that list's ordering logic (DWG readability first, honest-failure reporting before optimization, hardest cases last) still holds and is preserved inside the phase-by-phase scoping above.

### Additional risks introduced by identity resolution itself

Not present in the original Step 9 table, because they only exist once "resolve observations into one identity" is itself a fallible step rather than a lookup:

| Risk | Handling |
|---|---|
| **False merge** — two genuinely different bars share a mark/position pattern strongly enough to cluster into one `PhysicalIdentity` (e.g. two different upstand instances among `SS-GF-01(M)`'s four repeated groups, if position disambiguation is weaker than expected) | `resolution_confidence` must be computed from the *margin* between the best cluster assignment and the next-best alternative, not just the best score in isolation — a strong-looking match that's only marginally better than a second candidate is exactly the case `ambiguous_alternative_clusters` exists to surface |
| **False split** — one real bar's observations fail to cluster (e.g. a detail sketch's callout symbol doesn't parse, so its `detail_geometry` observation never links to the rest) and it silently becomes two incomplete `PhysicalIdentity` records instead of one complete one | `CrossViewQA` needs a check for suspiciously-thin `PhysicalIdentity.observations` (e.g. count=1 within a drawing set where every other identity has 3+) as a signal to review, not just a check for explicit unresolved fields |
| **Wrong attachment locus** — a hook detail attaches to the wrong end/bend of a multi-bend bar because its callout symbol reference is ambiguous or missing | Treat `AttachmentPoint.locus` as unresolved (not defaulted to `'end'` or any other guess) when the callout reference can't be parsed — same "absence is a fact to report" discipline as everywhere else in this project |

### What this addendum does not change

Steps 1-3 (drawing evidence, architecture understanding, human reasoning process), Step 7's Phase-12 placement decision, and Step 8's recommendation of an evidence-graph strategy over geometry-first or annotation-first all stand — this addendum is a refinement *within* the evidence-graph strategy (Strategy C), making explicit what "the graph connects" (physical objects, not drawings) and what "resolving the graph" geometrically means (per-aspect hierarchical composition, not spatial registration), which Step 8's original comparison correctly favored but didn't fully specify.

---

## Addendum 2 — Renaming the phase, and the "claims" relationship

**Still pure research. No code. No architecture modified.** This addendum renames Phase 12 and adds one precise structural refinement to Addendum 1's data model. It does not introduce a competing model — checked against Addendum 1's `PhysicalObservation`/`ObservationEdge`/`PhysicalIdentity` sketch, the object-centric graph described here is the same structure, sharpened in two ways worth recording explicitly.

### The phase is renamed

**Phase 12 — Physical Identity Resolution**, not "Cross-View Fusion." "Fusion" describes an operation on drawings (combine records from A and B). That was always a slightly inaccurate name for what Addendum 1's model actually does, which is: decide which observations describe the same pre-existing physical object, then let that object accumulate what each observation knows about it. The scope, phase number, and roadmap (12.0-12.4) from Addendum 1 are unchanged — only the name, because the name should describe the question being answered (*"which observations describe the same bar?"*), not the mechanism (*"drawings get merged"*). `docs/README.md`'s phase table and any future `docs/audits/phase12/` directory should use this name.

### "Fusion" vs. "claims" — a real distinction worth making precise

Addendum 1's `ObservationEdge` is a **pairwise, pre-resolution** signal: evidence that two observations *might* belong together, used to compute clusters. It's the right mechanism for the resolution step (12.1/12.2) — clustering is genuinely how you get from "N observations" to "which ones are the same bar" when you don't yet know the identities in advance.

What was implicit, and is worth making an explicit, separate relationship, is what exists **after** a `PhysicalIdentity` is resolved: each of its `observations` isn't just "in the cluster" — it is **making a specific, scoped claim** about the object, with its own confidence, independent of the clustering confidence that put it there:

```python
@dataclass
class Claim:
    """The post-resolution edge from one PhysicalObservation to the
    PhysicalIdentity it was resolved into. Distinct from ObservationEdge
    (which is about WHETHER two observations belong together); a Claim is
    about WHAT one observation, once resolved, actually asserts about the
    object -- e.g. one observation claims a diameter, another claims a
    hook angle, a third claims a position. This is what
    PhysicalIdentity.observations actually needs to carry, made explicit."""
    observation_uuid: UUID
    identity_uuid: UUID
    facts: Dict[str, Any]        # e.g. {'diameter': 16.0} or {'hook_angle': 90.0}
    claim_confidence: float      # confidence in THIS fact, independent of
                                  # resolution_confidence (the confidence that
                                  # this observation belongs to this identity at all)
```

This matters because it separates two different failure modes that Addendum 1's single `resolution_confidence` number would otherwise conflate: an observation can be *correctly* resolved to the right bar (high clustering confidence) while *contributing an unreliable fact* (e.g. a section view's drawn circle is a poor diameter estimate at that drawing's scale — low claim confidence on that one fact, even though "this section is definitely showing bar N7" is not in doubt). Phase 12.3's per-aspect authority table in Addendum 1 already implicitly does exactly this weighting per aspect; `Claim.claim_confidence` is what makes that table's logic operate on an explicit number instead of an implicit rule.

With `Claim` in place, the assembly step (12.3) is precisely: for each aspect (diameter, path, hook, position), take the highest-authority `Claim` that has that fact, per the table in Addendum 1 — i.e., *"bar geometry = plan-path claim + section-hook claim + schedule-diameter claim + schedule-quantity claim,"* which is exactly the composition already specified, now with a concrete edge type to hang each term on.

### Viewer implication (forward-looking, not in scope for Phase 12 itself)

Once `PhysicalIdentity` exists, the viewer's existing selection architecture already has the right shape to support object-centric highlighting, with no redesign — direct reuse, per the original research constraint to identify and reuse existing capability rather than replace it. `viewer/scene.py::SceneManager` already tracks one `selected_*_uuid` per entity kind (`selected_bar_uuid`, `selected_family_uuid`, `selected_component_uuid`, `selected_mesh_uuid`, `selected_assembly_uuid`, `selected_entity_uuid`) and fires one `on_selection_changed` event that `property_panel.py` listens to and renders a `"Provenance"` chain string from (e.g. `"Physical Bar -> Family -> Components -> CAD"`). A `selected_physical_identity_uuid` is a natural extension of that exact same enum-of-selection-kinds pattern, and its provenance chain is simply one level longer: `"Physical Identity -> Physical Bar (per drawing) -> Family -> Components -> CAD"`. Selecting the resolved 3D bar would look up its `PhysicalIdentity.observations`/`Claim`s and set every contributing drawing's corresponding selection state; selecting one drawing's annotation would look up which `PhysicalIdentity` (if any) it resolved into and highlight the siblings. This is noted here as a concrete, evidence-grounded acceptance-criterion candidate for whatever phase eventually wires Phase 12's output into the viewer — not something to build now, and not a change to the already-frozen Phase 11 viewer architecture, since it's additive to an existing extension point rather than a modification of it.

---

## Addendum 3 — The observation invariant, and Phase 12.2 redesign notes

**Still pure research/design guidance. No code beyond what's already implemented and frozen for Phase 12.1.**

### Standing acceptance criterion, applies to all of Phase 12

> **An observation must never carry a fact for an aspect it did not directly read off its source.** A plan observation may claim path/position/spacing; it must never claim a hook. A schedule observation may claim diameter/quantity/length; it must never claim position. A section observation may claim a bend/hook and a corroborating diameter; it must never claim spacing. Absence of a fact means "this observation doesn't know" — never a fact carrying a placeholder or `None` value standing in for "unknown."

This is now implemented and enforced, not just stated: `core/fusion/models.py::ObservationFact`/`PhysicalObservation.facts` (Phase 12.1, `docs/audits/phase12/12.1_observation_builder.md`) replaced the original flat `mark`/`diameter`/`spacing`/... fields specifically so a fact's *presence* is its *only* representation — there's no separate `diameter_source='missing'` flag that could disagree with an absent fact, no capability set that could drift from the values it's supposed to describe. `tests/test_phase12_observation_builder.py::check_observation_invariant` verifies this against real data (`N6`/`N7`, whose Phase 9 families carry no diameter, must produce zero `DIAMETER` facts) on every run. This rule binds Phase 12.2 onward as much as it bound 12.1: a candidate/hypothesis generator must reason only over facts observations actually have, and an evidence engine must never synthesize a fact to make a comparison possible.

### Phase 12.2 is a Hypothesis Generator, not a Candidate Generator

Renamed for the same reason Phase 12 itself was renamed in Addendum 2: the name should describe the epistemic state, not the mechanism. An observation does not generate identities — it generates **hypotheses**, each scored independently, none committed. This introduces one more type ahead of `PhysicalIdentity` (Phase 12.4):

```python
@dataclass
class IdentityHypothesis:
    """One observation's guess at which physical object it might belong
    to -- NOT a resolved identity. Exactly one rung below ObservationEdge
    (Addendum 1): an ObservationEdge says 'these two observations might be
    the same object'; an IdentityHypothesis is what a group of such edges
    looks like from one observation's point of view before Phase 12.4
    commits to anything. Mirrors Phase 8's AssociationCandidate -> Evidence
    -> resolved EngineeringObject pipeline one level up, deliberately --
    that shape is already proven in this codebase."""
    observation_uuid: UUID
    candidate_identity_key: str      # a provisional grouping key (e.g. mark+drawing_number),
                                      # NOT a committed PhysicalIdentity.uuid
    supporting_edges: List['ObservationEdge']
    score: float
```

### Candidate generation ordering: engineering context before spatial proximity

Spatial distance must not be the first filter. Across drawing types there is often no shared coordinate system at all (Addendum 1's finding, re-confirmed here) — but there is almost always shared *engineering context*, and it's cheap, symbolic, and already partially available from Phase 1's `ProjectManifest.relationships` (`floor -> element -> drawing_number -> [filenames]`). The ordering a Phase 12.2 implementation should use:

1. **Same `drawing_number`** (Phase 1's existing grouping — already computed, free to use, scopes everything that follows to one physical element).
2. **Same mark**, respecting `mark_namespace` (never compare a `self_decoding` mark against a `reference_code` mark as if they were the same kind of thing).
3. **Compatible `drawing_role`** (a `mould_instance` observation's `N7` and a `reinforcement_typical` observation's schedule entry are compatible *because* their roles are complementary, not despite it).
4. **Compatible facts** (do the aspects that both observations claim actually agree, where they overlap — e.g. two `DIAMETER` facts from different sources should roughly match).
5. **Spatial compatibility** — last, and only as corroboration once the above already narrowed the field, never as the initial filter. This directly reflects Addendum 1's finding that plan/section/detail views often aren't in a shared coordinate frame at all, so spatial distance is frequently not even computable, let alone a reliable first signal.

This ordering is a design note for whoever (or whichever future turn) implements Phase 12.2 — not implemented in this turn. Phase 12.1 remains the last frozen subphase.
