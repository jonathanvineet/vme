# Ground Truth Format

Ground truth is **engineer-authored, never generated**. The benchmark loads it read-only; nothing in `benchmark/` ever writes into a project's `ground_truth/` directory.

## Corpus layout

```
benchmark/corpus/<ProjectName>/
    drawings/            # the raw drawing package (.dxf/.dwg)
    ground_truth/
        identities.json  # required — the core labels
        bars.json        # optional — expected physical bars (reconstruction coverage)
        families.json    # optional — expected per-drawing families
        metadata.json    # required — who labeled it, when, from what source
```

## identities.json

One entry per **physical bar (or bar group)** the engineer can identify across the drawing set. `observations` lists where that physical object appears — each selector names a drawing and the mark under which the object appears there.

```json
[
  {
    "uuid": "gt-0001",
    "name": "Upstand U-bar, east kerb",
    "mark": "N7",
    "diameter": 16.0,
    "spacing": null,
    "role": "upstand_bar",
    "observations": [
      {"drawing": "SS-GF-01(M).dxf", "mark": "N7"},
      {"drawing": "SS-GF-01(R).dwg", "mark": "T16"}
    ],
    "expected_geometry": "u_bar",
    "notes": "Defined on the R sheet; positioned on the M sheet dimension chain."
  }
]
```

Selector semantics: a selector matches every pipeline `PhysicalObservation` whose `drawing_filename` equals `drawing` and whose MARK fact equals `mark`. If a drawing/mark pair is genuinely ambiguous (several same-mark families on one sheet), add `"index": <n>` — matches are sorted by observation UUID and the n-th (0-based) is taken. Unresolvable selectors are reported as explained failures, never silently dropped.

`diameter`/`spacing`/`mark` in the ground truth are the values the **engineer** asserts; engineering-coverage measures whether the pipeline recovered them, from any resolved observation.

## bars.json (optional)

```json
[
  {"mark": "T16", "count": 2, "diameter": 16.0}
]
```

Used only for reconstruction coverage (existence of recovered bars per mark — never geometry quality).

## families.json (optional)

```json
[
  {"drawing": "SS-GF-01(R).dwg", "mark": "T12", "expected_count": 6}
]
```

## geometry.json (optional — Phase 13.2 extension)

Per-bar expected geometry, for future geometric-fidelity metrics (diameter/spacing accuracy already come from `identities.json`; this adds shape-level truth). Only label what the engineer can actually assert from the drawings — leave out what isn't shown (the observation invariant applies to humans too).

```json
[
  {
    "gt_uuid": "gt-0001",
    "shape": "u_bar",
    "hooks": [{"end": "start", "angle_deg": 90, "note": "belongs to top reinforcement"}],
    "approx_length_mm": 2850,
    "continues_into": "P4",
    "splices": []
  }
]
```

No metric consumes `hooks`/`continues_into`/`splices` yet — they are captured now so labeling doesn't have to be redone when Phase 14 (semantics) needs them.

## notes.md (optional)

Free-form engineer commentary per project: ambiguities, drafting quirks, anything that resisted structured labeling. Read by humans, never parsed.

## metadata.json

```json
{
  "project_name": "Apollo Girls Hostel — PW panels",
  "source": "VME Precast / ES Structural Consultant",
  "labeled_by": "<engineer name>",
  "labeled_date": "2026-07-13",
  "label_confidence": "full | partial",
  "engineer_hours": 3.5,
  "notes": ""
}
```

`labeled_by` is required to be a person. A ground-truth file whose metadata says it was machine-generated is rejected by the loader. `engineer_hours` (labeling effort) is aggregated into corpus statistics so dataset growth and cost stay visible.

## Failure-bucket classification

Every benchmark failure must land in exactly one pipeline bucket — no generic "FAILED". The mapping from the framework's existing failure statuses:

| Benchmark status | Bucket | Meaning |
|---|---|---|
| selector `drawing_missing` | **Reader** | drawing absent/unreadable (check DWG converter, Phase 1 capabilities) |
| selector `mark_missing`, mark present in drawing text but no observation | **Recognition / Association** | geometry or annotation-association failed upstream of families (Phases 7-8) |
| selector `mark_missing`, mark genuinely absent from drawing | **Ground truth** | label error — fix the label, not the pipeline |
| GT outcome `missed` (resolved, no accepted identity) | **Identity** | pairs held at REVIEW/REJECTED (Phase 12.4 decisions carry the rationale) |
| GT outcome `split` / pipeline `false_merge` | **Identity** | clustering error (Phase 12.2-12.4) |
| bars.json mark unrecovered | **Geometry** | family existed but no physical bar built (Phase 10) |
| future: mesh checks | **Mesh** | reserved (mesh-completeness metric not yet implemented) |
