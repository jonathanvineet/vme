"""
tests/determinism_phase10.py

Extends tests/determinism.py's guarantee through Phase 10 reconstruction:
runs the full pipeline (Phase 1 -> Phase 10 mesh generation) N times on the
same drawing and asserts every run produces identical assemblies.json,
bars.json, meshes.json, and OBJ output. core/reconstruction/ has no
uuid4() calls (verified: all UUIDs are uuid5-derived), so this is expected
to already be deterministic -- this test exists to catch a regression if
that ever changes, the same role tests/determinism.py plays for Phase 7.

Usage:
    python tests/determinism_phase10.py <directory> [--runs N]

Exit codes:
    0 — all N runs produced identical output
    1 — nondeterminism detected
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile


def run_once(directory: str) -> str:
    with tempfile.TemporaryDirectory() as out_dir:
        env = os.environ.copy()
        subprocess.run(
            [sys.executable, "run_phase10.py", directory, "--debug"],
            check=True, capture_output=True, env=env,
        )
        # run_phase10.py writes to debug/phase10/<drawing>/ regardless of a
        # temp dir, so read from the known debug location instead of out_dir.
        base = None
        debug_root = os.path.join("debug", "phase10")
        for name in sorted(os.listdir(debug_root)):
            base = os.path.join(debug_root, name)
        if base is None:
            raise RuntimeError("Phase 10 did not produce a debug output directory")

        hasher = hashlib.sha256()
        for fname in ("assemblies.json", "bars.json", "meshes.json"):
            path = os.path.join(base, fname)
            with open(path) as f:
                data = json.load(f)
            hasher.update(json.dumps(data, sort_keys=True).encode("utf-8"))
        obj_path = os.path.join(base, "0001.obj")
        if os.path.exists(obj_path):
            with open(obj_path, "rb") as f:
                hasher.update(f.read())
        return hasher.hexdigest()


def run_determinism_check(directory: str, runs: int = 5) -> int:
    hashes = []
    for i in range(runs):
        h = run_once(directory)
        hashes.append(h)
        print(f"  run {i + 1:2d}/{runs}: {h}")

    unique = set(hashes)
    print(f"\nunique hashes: {len(unique)} / {runs} runs")
    if len(unique) == 1:
        print("PHASE 10 DETERMINISM CHECK PASSED ✅")
        return 0
    print("PHASE 10 DETERMINISM CHECK FAILED ❌")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/determinism_phase10.py <directory> [--runs N]")
        sys.exit(1)
    directory = sys.argv[1]
    runs = 5
    if "--runs" in sys.argv:
        runs = int(sys.argv[sys.argv.index("--runs") + 1])
    sys.exit(run_determinism_check(directory, runs))
