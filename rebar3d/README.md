# rebar3d — 2D/3D rebar reconstruction from DWG drawings

Reconstructs the rebar cage of a precast element (wall panel / solid slab) in 3D
from its reinforcement DWG drawing.

## How it works

1. **Convert** DWG → DXF with libredwg's `dwg2dxf` (`brew install libredwg`).
2. **Cluster views**: modelspace entities are grouped spatially (grid-hash
   connected components over geometry layers `S-RBAR`, `A-WALL`, `A-FLOR`…).
   The cluster with the most rebar entities is the elevation; the others are
   section cuts.
3. **Extract centerlines**: bars are drawn as double lines (true outline).
   Parallel line pairs separated by 5–34 mm become centerlines — the pair gap
   *is* the bar diameter. Concentric arc pairs become bends; touching pieces
   are chained into full bar shapes (hooks, U-bars). Hidden runs (inside
   concrete) are dashed; the dashes merge into the same rails, so bars come
   out continuous instead of fragmented.
4. **Recover depth (Z)**: sections whose outline matches the panel width
   (or height) are registered to the elevation by that shared axis. Circles on
   `S-RBAR` inside the cut are crossing bars: circle position along the section
   gives the bar's X (or Y), its offset inside the wall outline gives the true
   through-thickness Z. Bars without a circle match snap to the nearest
   observed Z-plane.
5. **Depth pairs**: the same bar position usually shows a section circle near
   *each* face — one physical bar per depth is emitted, so both mesh layers
   (horizontal + vertical on both faces) are modeled.
6. **U-bars**: sections draw edge wraps as a bend joining the two mesh depths
   (quarter-arcs across the thickness). Elevation bar pairs whose ends land on
   a bend profile are joined through it — one wrap makes a U, wraps at both
   ends close the pair into a link.
7. **Cast-in features**:
   - *Sleeves / corrugated pipes*: full circles on `A-WALL` inside the panel
     face (drawn as arc fragments) → green ringed through-thickness tubes.
   - *Corbels & steel embeds*: `M_Rectangular Corbel` / channel block inserts
     on `S-BEAM`; the elevation instance gives x/y, side-view instances give
     the protrusion depth.
   - *Lifting anchors & wire loops*: `RR spread anchor` / `Wire Loop` block
     inserts on `A-GENM` → orange boxes.
8. **Export**: per-panel model JSON, orthographic projection PNGs, and a
   self-contained three.js viewer (`viewer.html`).

## Viewer

- Bar Schedule (bottom right): per diameter — count, length, unit weight
  (d²/162 kg/m) and total; concrete weight at 2500 kg/m³. Lone unmatched
  pairings are excluded.
- **Resize module** (top right): enter a new W×H and apply — a split view
  shows the original (left) next to the modified panel (right). Mesh
  families are re-spaced at their drawn pitch (bar counts change with the
  size; end zones keep their tighter pitch), features/openings scale, and
  the schedule shows original vs modified steel + concrete weights.
- **⬇ DXF**: downloads the current (modified if resized) geometry as an
  R12 DXF — 3D bar centerlines on `S-RBAR`, outline + sleeve circles on
  `A-WALL`, corbels/embeds on `S-BEAM`, anchors/loops on `A-GENM`.
- **⬇ report**: standalone HTML report with the geometry, bar schedules
  (original and modified), weight comparison, and cast-in item counts.
- `viewer.html?w=3000&h=2930#PW-GF-09` applies a resize on load.

## Run

```sh
python3 -m rebar3d.cli "../DRAWINGS/PW-GF-02(R).dwg" "../DRAWINGS/PW-GF-09(R).dwg" \
    "../DRAWINGS/SS-GF-01(R).dwg" -o out
open out/viewer.html
```

Requires: python3 with `ezdxf`, `matplotlib`; `dwg2dxf` on PATH.

## Results on the Apollo drawings

| Panel | Size (mm) | Bars | U-bars | Sleeves | Anchors/loops | Corbels/embeds |
|---|---|---|---|---|---|---|
| PW-GF-02 | 3760×2930×160 | 326 | 87 | 10 | 5 + 21 | 2 embeds |
| PW-GF-09 | 4000×2930×160 | 407 | 51 | 10 | — | 1 corbel |
| PW-GF-45 | 2650×2930×160 | 158 | 47 | 7 | 6 | — |
| SS-GF-01 | 5200×2050×375* | 249 | — | — | 7 | — |

*SS-GF-01 is a slab with upturned edge beams — the overall depth includes
upstands; bottom mesh sits at 35–45 mm as expected.

## Known limitations

- Diagonal crack bars and unmatched shapes default to mid-thickness.
- In-plane bent shapes (perimeter bands, corbel hooks) keep their drawn
  elevation geometry at one depth.
- The two faces could be globally swapped (drawing doesn't state which side of
  a section cut is the mould face); relative layering is correct.
- Openings render as outline loops, not boolean cuts in the concrete volume.
- Concrete volume is the bounding box — notches/recesses from the mould (M)
  drawings are not yet composed in.
