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
   are chained into full bar shapes (hooks, U-bars).
4. **Recover depth (Z)**: sections whose outline matches the panel width
   (or height) are registered to the elevation by that shared axis. Circles on
   `S-RBAR` inside the cut are crossing bars: circle position along the section
   gives the bar's X (or Y), its offset inside the wall outline gives the true
   through-thickness Z. Bars without a circle match snap to the nearest
   observed Z-plane.
5. **Export**: per-panel model JSON, orthographic projection PNGs, and a
   self-contained three.js viewer (`viewer.html`).

## Run

```sh
python3 -m rebar3d.cli "../DRAWINGS/PW-GF-02(R).dwg" "../DRAWINGS/PW-GF-09(R).dwg" \
    "../DRAWINGS/SS-GF-01(R).dwg" -o out
open out/viewer.html
```

Requires: python3 with `ezdxf`, `matplotlib`; `dwg2dxf` on PATH.

## Results on the Apollo drawings

| Panel | Size (mm) | Bars | Z from sections | Z planes found |
|---|---|---|---|---|
| PW-GF-02 | 3760×2930×160 | 442 | 394 | 32/43 + 106/117/126 (two mesh faces) |
| PW-GF-09 | 4000×2930×160 | 495 | 389 | 32/42/51 + 104/125 |
| SS-GF-01 | 5200×2050×425* | 752 | 109 | 44/50/73 + 330/378 |

*SS-GF-01 is a slab with upturned edge beams — 425 is the overall depth
including upstands; bottom mesh sits at 44–50 mm as expected.

## Known limitations (v1)

- Bars with bends (U-bars, hooks) keep their elevation-plane geometry at a
  single Z; the true out-of-plane leg (wrapping the panel edge between the two
  mesh faces) is not yet folded into 3D.
- Diagonal crack bars and unmatched shapes default to mid-thickness.
- The two faces could be globally swapped (drawing doesn't state which side of
  a section cut is the mould face); relative layering is correct.
- Openings render as outline loops, not boolean cuts in the concrete volume.
- Concrete volume is the bounding box — notches/recesses from the mould (M)
  drawings are not yet composed in.
