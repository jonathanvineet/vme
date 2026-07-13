# Engineering Assumptions

The single source of truth for every engineering-domain assumption the pipeline makes. Each entry states the assumption, the evidence it rests on, where it's enforced in code, and its confidence. When an assumption is revised, update it here first — audits and code comments reference this document, not the other way round.

**Evidence base**: one drawing package (Apollo Girls Hostel, VME Precast / ES Structural Consultant — 8 machine-readable drawings, 3 visually-read PDFs). Every assumption generalizes from n=1 project, one consultant's drafting style, one naming convention. Statistical validation awaits the benchmark corpus (`benchmark/`).

## Drawing roles

| # | Assumption | Evidence | Enforced in | Confidence |
|---|---|---|---|---|
| A1 | A filename suffix `(R)` denotes a **Reinforcement drawing**: authoritative for bar mark, diameter, spacing, bar shape, and the reinforcement *pattern* of an element. | `PW-GF-09(R)` PDF (read visually); `SS-GF-01(R).dwg` (read via pipeline): both carry exclusively self-decoding T-marks with diameters/spacings. | `core/fusion/models.py::classify_drawing_role` | High within this convention; unknown across consultants |
| A2 | A filename suffix `(M)`, `(M1)`, `(M2)`… denotes a **Mould drawing**: authoritative for panel geometry, dimension chains, absolute building levels, erection marks, and embed/dowel *positions* — never for bar diameter/spacing. | `PW-GF-09(M1)/(M2)` PDFs; `SS-GF-01(M).dxf`: zero self-decoding marks, N-reference-codes + `LENGTH`/`UPSTAND`/`GF SSL` vocabulary. | same | High within this convention |
| A3 | One `(R)` sheet can be **typical for many element instances** (e.g. "REINFORCEMENT TYPICAL FOR: PW-GF-09 … PW-7F-09") — reinforcement pattern is shared; position/levels are per-instance from each `(M)` sheet. | `PW-GF-09(R)` PDF note, read verbatim. | Not yet enforced (no typical-note parser; named as future ANNOTATION evidence) | High that the mechanism exists; parsing unimplemented |

## Mark namespaces

| # | Assumption | Evidence | Enforced in | Confidence |
|---|---|---|---|---|
| A4 | `T<n>` marks are **self-decoding**: the mark itself encodes diameter in mm (T12 → 12mm). No lookup needed. | `PW-GF-09(R)` summary schedule cross-checks (T8→8mm rows etc.); `SS-GF-01(R)` families carry matching diameters. | `classify_mark_namespace` (`self_decoding`), reusing Phase 8's `DIA_PATTERN` | High (also standard BS-style detailing convention) |
| A5 | `N<n>` marks are **reference codes**: meaningless without a lookup (dowel/insert schedule, or the companion sheet). Never resolve an N-code's diameter from the code itself. | `PW-GF-09(M2)` Dowel Bar Schedule (N7→16mm×6) and Insert Schedule; `SS-GF-01(M)`'s N4/N6/N7 have no local definition. | `classify_mark_namespace` (`reference_code`); Phase 12.2 never matches across namespaces | High |
| A6 | Marks are **unique only within one drawing set/element**, never globally. `N4` on SS-GF-01 and `N4` on PW-GF-09 are unrelated. | `PW-GF-09`'s N4 = 50mm sleeve; `SS-GF-01`'s N4 = upstand bar region. Same code, different things. | `generate_hypotheses` scopes all pairing to `drawing_number` | High |

## View authority (which view is trusted for which fact)

| # | Aspect | Authoritative view | Corroborating (never primary) | Enforced |
|---|---|---|---|---|
| A7 | Bar mark, diameter, spacing | Reinforcement drawing / schedule row | Section's drawn circle diameter (flag mismatch, never average) | Partially: per-fact confidences exist; schedule parsing does not |
| A8 | XY path / centerline shape | Plan or elevation with to-scale geometry in one coordinate frame | Detail sketches, if dimensionally consistent | Phase 10 geometry recovery (within one drawing); cross-view not yet |
| A9 | Hook / bend detail | Detail view referenced by callout symbol, attached to a specific bar end/bend | Plan's local direction change at that locus | Not yet (no HOOK aspect — no real source exists in Phase 9 output) |
| A10 | 3D placement in the building | Mould sheet dimension chains + absolute levels (`GF SSL`, `1F SSL`) | — | Not yet (no LEVEL aspect — same reason) |
| A11 | Quantity | Schedule (explicit count) over detected geometry count | Detected member count from geometry | Partially: `quantity` fact = detected count today; schedule quantities unparsed |

## Cross-view correlation

| # | Assumption | Evidence | Enforced in | Confidence |
|---|---|---|---|---|
| A12 | Views cross-reference **symbolically** (numbered section markers, detail callouts, shared reference codes), not spatially. A section is routinely drawn in unrelated sheet space; no coordinate transform between views should be assumed. | `PW-GF-09(M1)` Section 1 placed in blank space; section-marker symbols 1/2/3 on both PW and SS sheets. | Phase 12.2: spatial distance is `polarity=UNKNOWN`, never a qualifying signal | High |
| A13 | Identity must be resolved **before** geometry is merged — never discover identity as a side effect of geometric overlap. | Design principle (research report core thesis); reinforced by A12. | Phase 12 ordering: 12.4 creates identities; reconstruction consumes them later; `identity_resolver.py` imports no reconstruction code (AST-tested) | Architectural invariant |
| A14 | An observation must never carry a fact its source view cannot directly show (a plan never claims a hook; a schedule never claims a position). | Observation invariant, Phase 12.1. | `_facts_for_family` + `check_observation_invariant` | Architectural invariant |
| A15 | Mixed evidence (agreement + conflict) must resolve to human review, not auto-merge or auto-reject. Absence of information is a fact to report, not a gap to fill. | Project-wide principle (Phase 7.6, 10.1, 12.4); N↔T pairs correctly at REVIEW. | `identity_resolver._decide` | Architectural invariant |

## Materials & constants observed (project-specific, NOT generalized)

Recorded for reference; the pipeline does not assume these — they came from one project's general notes (`PW-GF-09(R)`): Concrete M40, Steel Fe550, wall cover 30mm, corbel cover 25mm, stripping strength M20, lifting/erection M35.

## Revision & conflict rules

| # | Assumption | Status |
|---|---|---|
| A16 | When sheets disagree, the higher revision block (`Rev/Date/Chkd/Appd`) wins — never file mtime, never "most recent content". | Stated in research report Step 5; revision-block parsing unimplemented (all observed sheets are Rev 0). |
| A17 | Same-mark families within one sheet may be either the same physical bars in different views (elevation + section on one sheet) or genuinely distinct bar groups sharing a mark. **No current evidence distinguishes these** — see the unverified T16 identity in `known_limitations.md`. | Open question; the benchmark corpus ground truth is the intended resolution mechanism. |
