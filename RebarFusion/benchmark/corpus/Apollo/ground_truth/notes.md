# Apollo — labeling notes

**Status: DRAFT, pending engineer verification.** Prepared by an AI assistant from drawing evidence; every fact carries provenance; `engineer_hours: 0` is deliberate and stays 0 until a structural engineer reviews these labels.

## Evidence sources (in order of strength)

1. **Visual PDF reading** — `PW-GF-09(R).pdf`, `PW-GF-09(M1).pdf`, `PW-GF-09(M2).pdf` were read page-by-page during the Phase 12 research (rasterized via qlmanage). This is the only source for schedule contents (Dowel Bar Schedule: N7=16mm×6, N8=16mm×9; Insert Schedule; Weight Schedule) and for functional group descriptions (UBAR/Vertical/Horizontal/Ties/Hook).
2. **Raw DXF text entities** — extracted directly with ezdxf from the ODA-converted drawings, independent of the Phase 3-12 pipeline. This is the only source for the two sheets with no PDF (`PW-GF-02(R)`, `SS-GF-01(R)`).
3. **Never used as label evidence: pipeline output** (families, observations, identities). Ground truth derived from the system under test would be circular. The single unavoidable shared dependency is the DXF reader/ODA conversion itself.

## Exclusions from drawings/

- `banana.dwg` and `PW-GF-02(M1)-copy.dwg` — byte-identical to `PW-GF-02(M1).dwg` (sha256 `a33c74e8…14a6` all three, verified). Duplicates carry no information and the unparseable `banana` filename would poison drawing-role classification.
- `PW-GF-09(*).pdf` — print duplicates of the DWG sheets; no PDF reader is registered.
- `ProjectRepository/` — not a drawing.

## Known label-quality caveats

- **Same-mark granularity**: schema v1 selectors are `{drawing, mark}`, so the five distinct T8 functional groups on PW-GF-09(R) are one GT record with the breakdown in `families.json`. Physical-bar-level truth for same-mark groups needs either the `index` selector (opaque to engineers) or a schema extension — recorded as a discovered limitation, not worked around.
- **N↔T cross-sheet mapping deliberately absent** for SS-GF-01: no schedule in the package resolves N4/N6/N7, so no cross-sheet identity is asserted. UNKNOWN is the label.
- **PW-GF-02 mould sheets (M1/M2)** carry N-codes for embeds/inserts; without a visually-read schedule for that element (no PDF), those N-codes are not labeled as steel — only PW-GF-09's dowels are, because its schedule was actually read.

## A17 evidence (T16 grouping — UNRESOLVED)

`2 -T16` appears **8 times** on PW-GF-09(R), in two sheet regions (x≈-28.7k/-27.9k and x≈-21k/-22k). The pipeline's single ACCEPTED identity merged two T16 observations that are 22mm-long section-view symbols (bar cross-section markers, not drawn bar lengths), ~570mm apart, **each with its own `2-T16` label**. Two separately-labeled locations is evidence *leaning toward distinct physical bar groups* (i.e., the accept may be a false merge), but the alternative — the same pair of edge bars labeled at both faces of one section — cannot be excluded without reading the section geometry the way an engineer would. **Left unresolved; do not force.** See `docs/known_limitations.md`.
