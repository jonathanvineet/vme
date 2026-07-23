"""Convert DWG -> DXF via libredwg's dwg2dxf, caching results.

Independent of rebar3d/ — this project starts fresh and does not import
or modify anything under rebar3d/.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

CACHE_DIR = Path(__file__).parent / "out" / "dxf_cache"


def dwg_to_dxf(dwg_path: Path) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / (dwg_path.stem + ".dxf")
    if out.exists() and out.stat().st_mtime >= dwg_path.stat().st_mtime:
        return out
    subprocess.run(
        ["dwg2dxf", "-o", str(out), str(dwg_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return out
