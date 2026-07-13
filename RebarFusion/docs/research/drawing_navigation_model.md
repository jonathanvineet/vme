# How a structural engineer navigates a drawing package to understand one bar

**No code was written or modified.** Research only. This reframes the question the project has been asking — "how is a bar reconstructed" — as the prior question: how does an engineer *find* the information that gets composed into a bar. Every claim below is grounded in evidence already gathered this session (the full PW-GF-09(R)/(M1)/(M2) PDF reading, the SS-GF-01 N7 hand-trace, and the registration audit) — no new drawings were opened to write this. **Scope, stated as it has been every time**: one project, one consultant. The navigation *moves* described are directly observed; whether they generalize to other consultants' conventions is unanswered and unanswerable from this corpus.

## Method note: why this is the right question, evidenced, not asserted

The registration audit's closing line — "identity still has to be earned symbolically" — is the finding this document follows up on. If geometry can't be found by spatial proximity (proven: 62-2079mm noise across every sheet pair tested), then finding it happens some other way, and that way is observable in the drawings themselves: every drawing in this package carries **explicit navigation aids** — sheet titles, "TYPICAL FOR" scope notes, numbered section/erection markers, "REFER FOR..." cross-references, schedule tables keyed by reference code. These aren't reinforcement data. They're *wayfinding* data. The project has been extracting them as if they were engineering facts (marks, dimensions) without ever modeling their actual function: telling the reader where to look next.

## The navigation model

### Node types (what an engineer treats as one stop)

| Node type | Evidence it exists as a distinct stop | Observed in |
|---|---|---|
| **Reinforcement sheet** `(R)` | Self-contained: bar marks, shapes, spacings, cover, summary schedule, "TYPICAL FOR" note — an engineer can leave having understood the *reinforcement pattern* without opening anything else | `PW-GF-09(R).pdf` read in full |
| **Mould sheet, position** `(M1)` | Dimension chains, erection marks, absolute levels; explicitly states it does NOT carry reinforcement ("REFER FOR INDIVIDUAL MOULD DRAWING") | `PW-GF-09(M1).pdf` |
| **Mould sheet, schedule** `(M2)` | Dowel Bar Schedule, Insert Schedule, Weight Schedule, 3D isometric, Notch Detail — a *second* mould sheet exists specifically to hold the schedule tables `(M1)` deferred to | `PW-GF-09(M2).pdf` |
| **Section view** (within a sheet) | Numbered (`Section 1`-`5`), spatially separate from its parent elevation (registration audit: zero coordinate relationship) — reached only by number, never by position | `PW-GF-09(M1)` Section markers 1/2/3; SS-GF-01 same markers, same numbering scheme, cross-sheet |
| **Detail view** (within a sheet) | Lettered (`Detail-A`, `Detail-B`, `NOTCH DETAIL-A`), same non-spatial reachability as sections | `PW-GF-02(M2)`, `PW-GF-09(M2)` |
| **Schedule row** | A table row keyed by reference code, living on a specific sheet (`(M2)` for dowels/inserts, `(R)`'s own summary table for T-marks by diameter) | Dowel Bar Schedule: N7→16mm×6 |
| **Scope note** | Free text asserting one sheet's content applies to multiple physical elements | "REINFORCEMENT TYPICAL FOR: PW-GF-09, PW-1F-09, ... PW-7F-09" |

### Link types (how an engineer moves between stops)

| Link type | Mechanism | Mandatory or optional | Evidence |
|---|---|---|---|
| **Sheet-suffix link** | Filename/title-block convention: `(R)` ↔ `(M1)` ↔ `(M2)` share a `drawing_number` | Mandatory to find the sheet set at all | A1-A3; Phase 1's existing `drawing_number` grouping already models this |
| **Numbered section-marker link** | A number on the parent view; the target section is titled with the same number | Mandatory for section-level facts (hook, cover) — no other path reaches them | Section markers 1-5, PW-GF-09(M1); confirmed structurally non-spatial by the registration audit |
| **Lettered detail-callout link** | Same mechanism, letters instead of numbers | Mandatory for bend/anchorage facts | `NOTCH DETAIL-A`/`-B` |
| **Reference-code → schedule-row link** | An N-code (or dimension-row label) on a position sheet, resolved by finding the matching row on a schedule sheet | Mandatory when the mark is a reference code (A5) — this is the *only* path to diameter for N-marks | N7 → Dowel Bar Schedule row (PW-GF-09); **absent** for SS-GF-01's N-codes — no schedule exists in that package, confirmed by the corpus audit (VQ-002 exists precisely because this link is missing) |
| **Self-decoding mark** | No link needed — the mark text itself is the fact | N/A (terminates navigation for diameter) | T12 = 12mm, no lookup |
| **Scope-note link** | A sentence naming other elements the current sheet's content applies to | Optional to follow (only needed when working a *different* element than the one at hand) but mandatory to *notice*, else the engineer wrongly assumes each element has its own reinforcement sheet | "TYPICAL FOR" note; PW-GF-02(M1)'s 6 repeated erection-mark instances (registration audit) is the mould-side symptom of this same fact — one reinforcement pattern, many positioned instances |
| **Coordinate proximity** | Spatial nearness between a label and geometry | **Never mandatory, weak-optional at best** | Registration audit: 62-2079mm noise; A12 |

### The navigation graph, structurally

```
DrawingNode(sheet_id, role)
    --sheet_suffix_link-->  DrawingNode (same drawing_number, different role)
    --section_marker_link--> SectionNode (numbered, non-spatial target)
    --detail_callout_link-->  DetailNode (lettered, non-spatial target)
    --reference_code_link-->  ScheduleRow (only for reference-code marks; may not exist)
    --scope_note_link-->      DrawingNode* (other elements this sheet's content covers)

ScheduleRow(reference_code, sheet_id)
    --resolves--> EngineeringFact(diameter | quantity | cut_length | ...)
```

This is a **navigation graph with typed edges**, not a spatial index and not a geometry graph. It is deliberately close to Phase 1's already-existing `ProjectManifest.relationships` (`floor → element → drawing_number → [filenames]`) plus Phase 8's `AnnotationParser` output (which already tokenizes marks, but currently treats every mark identically — the model above requires distinguishing which marks are *links* (reference codes, requiring resolution) from which are *terminal facts* (self-decoding marks, requiring none) — exactly A4/A5, now framed as a link-type distinction rather than a data-type distinction.

## Walking three real navigation paths (evidenced, not hypothetical)

### Path A — a T-mark bar on PW-GF-09 (the well-behaved case)

```
Open PW-GF-09(R)
  → read "T8 UBAR @150 mm" directly on the elevation
  → mark is self-decoding: diameter=8mm, no further link needed
  → spacing is on the same label: 150mm, no further link needed
  → shape read directly from the drawn U-bar geometry on this sheet
  → cover read from the sheet's general note ("Wall 30mm")
  → STOP: every fabrication-required fact has a source, on ONE sheet
```
Zero cross-sheet navigation required. This is why T-mark bars produced usable pipeline observations without any identity-resolution machinery — the mark IS a self-contained answer.

### Path B — N7 dowel bar on PW-GF-09 (the reference-code case)

```
Open PW-GF-09(M1)
  → find dimension-chain row labeled "N7"
  → position known; diameter UNKNOWN (N-codes are not self-decoding)
  → sheet-suffix link: same drawing_number has an (M2)
Open PW-GF-09(M2)
  → find Dowel Bar Schedule
  → row "N7": 16mm dia, 6 nos.
  → STOP: identity (N7), position (M1), diameter+quantity (M2 schedule) — three sheets, one bar
```
Two cross-sheet hops, both via typed links (sheet-suffix, then implicit "this schedule resolves that reference-code"), zero spatial reasoning.

### Path C — N7 on SS-GF-01 (the incomplete case — this is why VQ-002 exists)

```
Open SS-GF-01(M)
  → find dimension-chain row labeled "N7", four instances, one with a placement chain
    (50|220|255|500|500|255|220|50 = 2050, matches LENGTH — internally consistent)
  → position known; diameter UNKNOWN
  → sheet-suffix link: same drawing_number has an (R)
Open SS-GF-01(R)
  → search for a schedule table resolving "N7" ... NONE EXISTS in this package
  → fall back to the weak-optional coordinate-proximity link (registration audit: unreliable)
  → find "T8 @200 mm" label near the expected region (11mm from the row band —
    inside the already-measured 62-421mm noise band, so: a candidate, not a resolution)
  → CANNOT STOP cleanly: no mandatory link resolves this bar's diameter.
    An engineer here either (a) has access to something this corpus doesn't (a BBS,
    a separate schedule sheet, or site knowledge), or (b) makes the same
    weakly-corroborated inference the pipeline/trace made, or (c) issues an RFI.
```
**This path is the evidence for VQ-002's honest status.** The navigation model doesn't just explain why N7's diameter is hard to resolve — it explains *why the resolution mechanism a human would actually reach for (a schedule) is structurally absent from this package*, which is a materially different, more precise claim than "diameter unknown."

## Answering the posed questions directly

- **What sheet do they open first?** The `(R)` sheet, when the goal is "understand the reinforcement" — it's self-contained for self-decoding marks and states its own scope ("TYPICAL FOR"). The `(M1)` sheet, when the goal is "place a specific physical instance." Evidence: `(R)`'s content is a complete, standalone reinforcement story (Path A); `(M1)`'s is not (it explicitly defers, "REFER FOR INDIVIDUAL MOULD DRAWING").
- **What symbols do they follow?** Numbered section markers, lettered detail callouts, reference codes into schedule tables. Never raw coordinates (registration audit).
- **Which references are mandatory?** Sheet-suffix (to find the set at all), section/detail markers (for anything only a section/detail shows — hooks, cover, bend radius), reference-code→schedule (for any non-self-decoding mark's diameter/quantity).
- **Which references are optional?** Scope notes are optional to *follow* (only relevant if working a different instance) but not optional to *notice* — missing it causes the "these are four different bars" mistake the very first Phase 12 research explicitly warned against.
- **What information is expected to be absent on each drawing type?** Exactly the authority matrix already in `engineering_assumptions.md` (A7-A11), now understood as *designed* absence, not incompleteness — `(M1)` is missing reinforcement data on purpose, `(R)` is missing absolute levels on purpose. An engineer doesn't treat these absences as errors; the software currently has no way to distinguish "absent because not this sheet's job" from "absent because missing."
- **What is looked up versus inferred?** Looked up: anything reachable via a mandatory link (schedule rows, section/detail content). Inferred: only the weak-optional coordinate-proximity fallback, used *only* when a mandatory link doesn't exist in the package (Path C) — and even then, held as a candidate requiring confirmation, never asserted.
- **When do they stop?** When every fabrication-required aspect (identity, diameter, quantity/spacing, shape/bends, hook if applicable, cut length) has a source reachable by a mandatory link. Path A stops in one sheet. Path B stops in two. Path C **cannot stop** — and correctly reports that, rather than fabricating a diameter. This "stop condition" is exactly Phase 12's ACCEPTED/REJECTED/REVIEW distinction, now understood as **navigation completeness**, not evidence-score thresholding: an identity is REVIEW not because its evidence score is mediocre, but because a mandatory link (a schedule that would resolve it) is structurally missing from the package.

## What this changes about the Phase 14 geometry-composition design

`docs/research/phase14_geometry_composition.md` is not wrong, but it is **downstream of a step that doesn't exist yet**. Its authority matrix (§2) already encodes *which sheet owns which fact* — that's a navigation conclusion, correctly reached, but the document assumed the *path to that sheet* was already available. It isn't: nothing in the frozen pipeline models sheet-suffix grouping as a *traversable link* (Phase 1 computes the grouping but nothing walks it), nothing models section/detail markers as links at all (they're currently just TEXT entities, tokenized identically to everything else), and nothing distinguishes a self-decoding mark (terminal) from a reference code (a link requiring resolution) at the *link* level — Phase 12.1's `mark_namespace` comes close but was framed as a fact-classification, not a navigation-edge-type.

**Revised sequencing** (research only — no roadmap phase is being started by writing this): the navigation graph is prior to composition, and quite possibly prior to a meaningful next iteration of identity resolution itself, because Path B/C show the graph would have directly produced the N7→dowel-schedule link Phase 12's evidence machinery currently has no way to construct (it can only compare facts *already extracted*, not follow the sheet-suffix→schedule-table path that produces the fact in the first place). This reframes the earlier "smallest missing piece" conclusion from the N7 trace (a shared-frame check) — that conclusion is now understood as **one weak-optional link among several, and not the mandatory one that actually resolves Path B**. The mandatory, evidenced, higher-value missing piece is: **model sheet-suffix and reference-code→schedule as explicit, followable links, and parse schedule tables into resolvable rows.** That is a navigation-graph capability, not a spatial one — consistent with, and a sharper version of, this session's repeated finding that spatial proximity keeps underperforming symbolic reference-following.

## Open research questions (not implemented, recorded)

- **RQ-N1**: is the sheet-suffix/schedule-table link sufficient to resolve *most* reference-code marks in a typical package, or was PW-GF-09 unusually complete (it has both `(M1)` and `(M2)`) while SS-GF-01 (Path C) is the more common case? Unanswerable from one project.
- **RQ-N2**: how does an engineer represent "I looked, the schedule doesn't exist for this element" versus "I haven't looked yet"? The corpus/benchmark's `drawing_missing`/`mark_missing` selector-failure vocabulary (Phase 13.1) already distinguishes these at the ground-truth level; whether the same vocabulary should become the navigation graph's own edge-resolution-failure vocabulary is a design question for whenever this becomes implementation.
- **RQ-N3**: this document treats scope notes ("TYPICAL FOR") as parseable free text; no extractor exists or was attempted here. Confirming the note's exact grammar across more than one example (Apollo has exactly one) is needed before assuming it generalizes.
