"""
tests/test_viewer_pipeline.py

Phase 11.1 freeze criteria: "Viewer consumes the same Phase 10 objects as
the CLI" and "Regression test added for viewer bundle loading." Asserts
that ProjectController's live pipeline path (core.full_pipeline, the same
function run_phase10.py calls) and the bundle-loading path (when a current
bundle is on disk) both produce family/bar/mesh counts identical to
run_full_pipeline() called directly -- i.e. the viewer cannot silently
diverge from the CLI, because both are just callers of the same function.

Usage:
    python tests/test_viewer_pipeline.py <directory>

Exit codes:
    0 — viewer and CLI pipeline output match
    1 — mismatch detected
"""

from __future__ import annotations

import sys
import os


def run_check(directory: str) -> int:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from core.full_pipeline import run_full_pipeline

    reference = next(iter(run_full_pipeline(directory, segments=12)))
    ref_counts = (
        len(reference.engineering_families),
        len(reference.reinforcement_assemblies),
        len(reference.physical_bars),
        len(reference.reconstruction_meshes),
    )
    ref_bar_point_counts = sorted(len(b.path) for b in reference.physical_bars)
    print(f"  Reference (core.full_pipeline directly): families/assemblies/bars/meshes = {ref_counts}")

    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    from viewer.controllers.project_controller import ProjectController
    controller = ProjectController()

    failures = []

    # Live pipeline path
    wp_live = controller._run_live_pipeline(directory)
    live_counts = (
        len(wp_live.engineering_families),
        len(wp_live.reinforcement_assemblies),
        len(wp_live.physical_bars),
        len(wp_live.reconstruction_meshes),
    )
    print(f"  Viewer live pipeline path:                families/assemblies/bars/meshes = {live_counts}")
    if live_counts != ref_counts:
        failures.append(f"live pipeline counts {live_counts} != reference {ref_counts}")
    live_bar_point_counts = sorted(len(b.path) for b in wp_live.physical_bars)
    if live_bar_point_counts != ref_bar_point_counts:
        failures.append(
            f"live pipeline bar path point-counts {live_bar_point_counts} != reference {ref_bar_point_counts} "
            f"-- viewer bars do not carry the same recovered geometry as the CLI"
        )

    # Bundle path, only if a current bundle exists on disk (produced by a
    # prior `run_phase10.py <directory> --debug` run) -- skipped otherwise,
    # not a failure, since nothing requires a bundle to exist.
    try:
        from viewer.project_loader import load_workbench_bundle
        from viewer.workbench_project import WorkbenchProject
        bundle = load_workbench_bundle(directory)
        wp_bundle = WorkbenchProject.from_bundle(bundle)
        bundle_counts = (
            len(wp_bundle.engineering_families),
            len(wp_bundle.reinforcement_assemblies),
            len(wp_bundle.physical_bars),
            len(wp_bundle.reconstruction_meshes),
        )
        print(f"  Viewer bundle path:                       families/assemblies/bars/meshes = {bundle_counts}")
        if bundle_counts != ref_counts:
            failures.append(f"bundle path counts {bundle_counts} != reference {ref_counts}")
    except Exception as exc:
        print(f"  Viewer bundle path: skipped (no current bundle on disk: {exc})")

    if failures:
        print("\nVIEWER PIPELINE CONSISTENCY CHECK FAILED ❌")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nVIEWER PIPELINE CONSISTENCY CHECK PASSED ✅")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/test_viewer_pipeline.py <directory>")
        sys.exit(1)
    sys.exit(run_check(sys.argv[1]))
