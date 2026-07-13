"""
benchmark/loaders/project_loader.py — BenchmarkProject.

Loads one corpus project: runs the frozen Phase 1-12 pipeline over its
drawings/ directory (read-only — nothing here alters pipeline behavior)
and loads the engineer-authored ground truth alongside it.

Evaluation layer only: this module never modifies pipeline output, never
writes into ground_truth/, and never generates ground truth.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from core.full_pipeline import run_pipeline_through_phase9, build_reconstruction
from core.fusion.observation_builder import build_observations
from core.fusion.hypothesis_generator import generate_hypotheses
from core.fusion.evidence_engine import score_hypotheses
from core.fusion.identity_resolver import resolve_identities
from core.fusion.models import ASPECT_MARK


@dataclass
class GroundTruthIdentity:
    uuid: str
    name: str
    mark: Optional[str]
    diameter: Optional[float]
    spacing: Optional[float]
    role: Optional[str]
    observations: List[Dict[str, Any]]     # selectors: {"drawing", "mark", optional "index"}
    expected_geometry: Optional[str] = None
    notes: str = ""


@dataclass
class SelectorResolution:
    """One ground-truth observation selector, resolved (or not) against
    pipeline observations — with the reason when it fails, so recall loss
    is always explainable."""
    selector: Dict[str, Any]
    observation_uuids: List[UUID] = field(default_factory=list)
    status: str = "resolved"       # 'resolved' | 'drawing_missing' | 'mark_missing' | 'index_out_of_range'
    reason: str = ""


@dataclass
class BenchmarkProject:
    name: str
    path: str
    metadata: Dict[str, Any]
    gt_identities: List[GroundTruthIdentity]
    gt_bars: List[Dict[str, Any]]
    gt_families: List[Dict[str, Any]]
    observations: List[Any]                 # PhysicalObservation
    decisions: List[Any]                    # ResolutionDecision
    identities: List[Any]                   # PhysicalIdentity
    physical_bars: List[Any]                # Phase 10 output (only if bars.json present)
    drawings_processed: int = 0


class GroundTruthError(ValueError):
    pass


def _load_json(path: str, default):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_project(project_dir: str) -> BenchmarkProject:
    drawings_dir = os.path.join(project_dir, "drawings")
    gt_dir = os.path.join(project_dir, "ground_truth")
    if not os.path.isdir(drawings_dir):
        raise FileNotFoundError(f"{project_dir!r} has no drawings/ directory")

    metadata = _load_json(os.path.join(gt_dir, "metadata.json"), {})
    labeled_by = str(metadata.get("labeled_by", "")).strip().lower()
    if labeled_by in ("", "auto", "generated", "machine", "pipeline"):
        raise GroundTruthError(
            f"{project_dir!r}: ground truth must be engineer-authored -- "
            f"metadata.json needs a real labeled_by (got {metadata.get('labeled_by')!r})"
        )

    gt_identities = [
        GroundTruthIdentity(
            uuid=e["uuid"], name=e.get("name", e["uuid"]), mark=e.get("mark"),
            diameter=e.get("diameter"), spacing=e.get("spacing"), role=e.get("role"),
            observations=e.get("observations", []),
            expected_geometry=e.get("expected_geometry"), notes=e.get("notes", ""),
        )
        for e in _load_json(os.path.join(gt_dir, "identities.json"), [])
    ]
    gt_bars = _load_json(os.path.join(gt_dir, "bars.json"), [])
    gt_families = _load_json(os.path.join(gt_dir, "families.json"), [])

    results = list(run_pipeline_through_phase9(drawings_dir))
    physical_bars: List[Any] = []
    if gt_bars:
        for result in results:
            build_reconstruction(result)
            physical_bars.extend(result.physical_bars or [])

    observations = build_observations(results)
    hypotheses = generate_hypotheses(observations)
    scored = score_hypotheses(hypotheses, observations)
    decisions, identities = resolve_identities(scored, observations)

    return BenchmarkProject(
        name=os.path.basename(os.path.normpath(project_dir)),
        path=project_dir, metadata=metadata,
        gt_identities=gt_identities, gt_bars=gt_bars, gt_families=gt_families,
        observations=observations, decisions=decisions, identities=identities,
        physical_bars=physical_bars, drawings_processed=len(results),
    )


def resolve_selector(selector: Dict[str, Any], observations: List[Any]) -> SelectorResolution:
    drawing = selector.get("drawing")
    mark = selector.get("mark")
    drawing_obs = [o for o in observations if o.drawing_filename == drawing]
    if not drawing_obs:
        return SelectorResolution(
            selector=selector, status="drawing_missing",
            reason=f"no observations from drawing {drawing!r} "
                   f"(drawing unreadable, absent, or produced no families)",
        )
    matches = sorted(
        (o for o in drawing_obs
         if o.fact(ASPECT_MARK) and o.fact(ASPECT_MARK).value == mark),
        key=lambda o: str(o.uuid),
    )
    if not matches:
        present = sorted({o.fact(ASPECT_MARK).value for o in drawing_obs if o.fact(ASPECT_MARK)})
        return SelectorResolution(
            selector=selector, status="mark_missing",
            reason=f"drawing {drawing!r} has observations but none marked {mark!r} "
                   f"(marks present: {present})",
        )
    if "index" in selector:
        idx = selector["index"]
        if idx >= len(matches):
            return SelectorResolution(
                selector=selector, status="index_out_of_range",
                reason=f"selector index {idx} but only {len(matches)} match(es)",
            )
        matches = [matches[idx]]
    return SelectorResolution(selector=selector, observation_uuids=[o.uuid for o in matches])
