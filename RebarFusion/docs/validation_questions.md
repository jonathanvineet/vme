# Validation Questions

Engineering ambiguities awaiting an engineer's answer. These are **not software defects or known limitations** — the software behaved correctly by refusing to decide them; they are questions about the physical structure that only drawing-reading expertise (or site knowledge) can settle. Each answer feeds back into `benchmark/corpus/` ground truth and, where warranted, `docs/engineering_assumptions.md`.

Rules: a VQ is never closed by the pipeline's own output; a VQ that turns out to be a software bug graduates to a defect report instead; resolved VQs stay here with their answer, dated, as precedent for similar cases.

---

## VQ-001 — Are PW-GF-09(R)'s two labeled T16 cross-sections the same physical bars? (OPEN)

**The question, precisely**: on `PW-GF-09(R)`, two bar cross-section symbols at (-28469, 3711) and (-27861, 3697) — ~570mm apart, each with its own `2 -T16` annotation — were merged by the pipeline into its single ACCEPTED identity. Are they (a) the same pair of T16 edge bars shown at two positions (e.g. both faces of one section) → merge correct, or (b) two distinct 2-T16 groups → the project's first measured false merge?

**Evidence so far** (Phase 13.2, `benchmark/corpus/Apollo/ground_truth/notes.md`): `2 -T16` appears 8 times on the sheet in two regions; the merged observations are 22mm section-view symbols, not drawn bar lengths; unanimous fact agreement between them (same mark/diameter/shape/orientation/length/quantity) is exactly what *either* interpretation predicts, so pipeline evidence cannot discriminate. Leaning (b) on the two-separate-labels reading, but not provable without engineer-level reading of the section.

**Why it matters**: this is the only ACCEPTED identity on real data — whether the resolver's first real accept was right or wrong calibrates trust in the v1 decision rule. Formerly tracked as assumption A17 (`docs/engineering_assumptions.md`) and a `known_limitations.md` entry; it lives here now because it is an engineering ambiguity, not a limitation of the software.

**Resolution path**: a structural engineer reads the PW-GF-09(R) section views (the PDF is in `test_project/`), answers (a) or (b), and the Apollo ground truth gains either a confirmed 2-bar identity or a false-merge label — moving precision off its current value in the next `benchmark/HISTORY.md` milestone either way.

---

## VQ-002 — Is SS-GF-01's N7 the `T8 @200 mm` upstand reinforcement? (OPEN)

**The question, precisely**: the manual N7 trace (`docs/research/apollo_n7_trace.md`) established that SS-GF-01's (M) and (R) sheets share a coordinate frame (A-FLOR outline extents identical to the millimeter; section markers 1/2/3 co-located), and that at the co-located section group (x=84345), the (R) label `T8 @200 mm` at (83584, 4440) sits 11mm from the (M) sheet's N7 dimension-row band (y=4429), with nothing else labeling that band. Does N7 therefore denote T8 U-bars at 200 centers — i.e., is the upstand reinforcement 8mm bars @ 200mm?

**Evidence so far**: one strong co-location (11mm in a shared frame), one weak corroboration (the x=78643 group's (R) labels sit lower in the section), and one non-check (the enlarged x=90128 upstand detail is (M)-only). The N7 placement chains (50|220|255|500|500|255|220|50 = 2050, matching LENGTH exactly) are independently solid.

**Why it matters**: if confirmed, this becomes the first resolved N-code→T-mark mapping in the corpus, the Apollo ground truth gains its first cross-sheet identity (`gt-ss01-n7` gains an (R)-sheet observation and a diameter), and it validates the shared-frame co-location mechanism as a legitimate evidence source (the trace's "smallest missing piece").

**Resolution path**: an engineer confirms or corrects the reading against the sheets; either answer updates `benchmark/corpus/Apollo/ground_truth/identities.json` and, if confirmed, refines assumption A12's scope in `docs/engineering_assumptions.md` (shared frames exist for same-element sheet pairs in this convention).
