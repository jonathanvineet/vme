# Validation Questions

Engineering ambiguities awaiting an engineer's answer. These are **not software defects or known limitations** — the software behaved correctly by refusing to decide them; they are questions about the physical structure that only drawing-reading expertise (or site knowledge) can settle. Each answer feeds back into `benchmark/corpus/` ground truth and, where warranted, `docs/engineering_assumptions.md`.

Rules: a VQ is never closed by the pipeline's own output; a VQ that turns out to be a software bug graduates to a defect report instead; resolved VQs stay here with their answer, dated, as precedent for similar cases.

---

## VQ-001 — Are PW-GF-09(R)'s two labeled T16 cross-sections the same physical bars? (OPEN)

**The question, precisely**: on `PW-GF-09(R)`, two bar cross-section symbols at (-28469, 3711) and (-27861, 3697) — ~570mm apart, each with its own `2 -T16` annotation — were merged by the pipeline into its single ACCEPTED identity. Are they (a) the same pair of T16 edge bars shown at two positions (e.g. both faces of one section) → merge correct, or (b) two distinct 2-T16 groups → the project's first measured false merge?

**Evidence so far** (Phase 13.2, `benchmark/corpus/Apollo/ground_truth/notes.md`): `2 -T16` appears 8 times on the sheet in two regions; the merged observations are 22mm section-view symbols, not drawn bar lengths; unanimous fact agreement between them (same mark/diameter/shape/orientation/length/quantity) is exactly what *either* interpretation predicts, so pipeline evidence cannot discriminate. Leaning (b) on the two-separate-labels reading, but not provable without engineer-level reading of the section.

**Why it matters**: this is the only ACCEPTED identity on real data — whether the resolver's first real accept was right or wrong calibrates trust in the v1 decision rule. Formerly tracked as assumption A17 (`docs/engineering_assumptions.md`) and a `known_limitations.md` entry; it lives here now because it is an engineering ambiguity, not a limitation of the software.

**Resolution path**: a structural engineer reads the PW-GF-09(R) section views (the PDF is in `test_project/`), answers (a) or (b), and the Apollo ground truth gains either a confirmed 2-bar identity or a false-merge label — moving precision off its current value in the next `benchmark/HISTORY.md` milestone either way.
