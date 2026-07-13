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

## metadata.json

```json
{
  "project_name": "Apollo Girls Hostel — PW panels",
  "source": "VME Precast / ES Structural Consultant",
  "labeled_by": "<engineer name>",
  "labeled_date": "2026-07-13",
  "label_confidence": "full | partial",
  "notes": ""
}
```

`labeled_by` is required to be a person. A ground-truth file whose metadata says it was machine-generated is rejected by the loader.
