"""
benchmark/metrics/coverage_metrics.py — observation, engineering, and
reconstruction coverage, plus corpus statistics.

Coverage metrics measure recovery/existence only, never quality:
reconstruction coverage asks "does a recovered bar with this mark exist,"
not whether its geometry is right (geometry quality needs per-bar
geometric ground truth, which this corpus format doesn't capture yet).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from benchmark.loaders.project_loader import BenchmarkProject, resolve_selector
from core.fusion.models import (
    ASPECT_DIAMETER, ASPECT_MARK, ASPECT_ORIENTATION, ASPECT_QUANTITY,
    ASPECT_SHAPE, ASPECT_SPACING,
)

# GT field -> the observation aspect that recovers it
_ENGINEERING_FIELDS = {
    "mark": ASPECT_MARK,
    "diameter": ASPECT_DIAMETER,
    "spacing": ASPECT_SPACING,
    "expected_geometry": ASPECT_SHAPE,
}


@dataclass
class CoverageDetail:
    gt_uuid: str
    expected: List[str] = field(default_factory=list)
    recovered: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)


@dataclass
class CoverageMetrics:
    observation_coverage: Optional[float]
    observation_note: str
    engineering_coverage: Optional[float]
    engineering_details: List[CoverageDetail] = field(default_factory=list)
    reconstruction_coverage: Optional[float] = None
    reconstruction_note: str = ""
    reconstruction_details: List[Dict[str, Any]] = field(default_factory=list)


def compute_coverage(project: BenchmarkProject) -> CoverageMetrics:
    # --- Observation coverage: GT selectors resolved / GT selectors total ---
    total_selectors = 0
    resolved_selectors = 0
    for gt in project.gt_identities:
        for selector in gt.observations:
            total_selectors += 1
            if resolve_selector(selector, project.observations).status == "resolved":
                resolved_selectors += 1
    if total_selectors:
        observation_coverage = round(resolved_selectors / total_selectors, 3)
        observation_note = f"{resolved_selectors}/{total_selectors} ground-truth observation selectors resolved"
    else:
        observation_coverage = None
        observation_note = "undefined: ground truth references no observations"

    # --- Engineering coverage: GT-asserted facts recovered anywhere among
    #     the GT identity's resolved observations ---
    details: List[CoverageDetail] = []
    recovered_total = expected_total = 0
    for gt in project.gt_identities:
        resolved_obs = []
        for selector in gt.observations:
            r = resolve_selector(selector, project.observations)
            resolved_obs.extend(r.observation_uuids)
        obs_objects = [o for o in project.observations if o.uuid in set(resolved_obs)]

        detail = CoverageDetail(gt_uuid=gt.uuid)
        for field_name, aspect in _ENGINEERING_FIELDS.items():
            gt_value = getattr(gt, field_name if field_name != "expected_geometry" else "expected_geometry")
            if gt_value is None:
                continue
            detail.expected.append(field_name)
            expected_total += 1
            values = [o.fact(aspect).value for o in obs_objects if o.fact(aspect)]
            if field_name == "mark":
                hit = gt_value in values
            elif field_name == "expected_geometry":
                hit = gt_value in values
            else:
                hit = any(abs(float(v) - float(gt_value)) < 1e-6 for v in values)
            if hit:
                detail.recovered.append(field_name)
                recovered_total += 1
            else:
                detail.missing.append(field_name)
        details.append(detail)
    engineering_coverage = round(recovered_total / expected_total, 3) if expected_total else None

    # --- Reconstruction coverage: GT bars whose mark exists among recovered
    #     physical bars (existence only) ---
    reconstruction_coverage = None
    reconstruction_note = "no bars.json ground truth supplied"
    recon_details: List[Dict[str, Any]] = []
    if project.gt_bars:
        recovered_marks = {b.mark for b in project.physical_bars}
        hits = 0
        for bar in project.gt_bars:
            found = bar.get("mark") in recovered_marks
            hits += found
            recon_details.append({
                "mark": bar.get("mark"), "expected_count": bar.get("count"),
                "recovered": found,
                "reason": "" if found else f"no reconstructed physical bar carries mark {bar.get('mark')!r}",
            })
        reconstruction_coverage = round(hits / len(project.gt_bars), 3)
        reconstruction_note = f"{hits}/{len(project.gt_bars)} ground-truth bar marks have >=1 recovered physical bar"

    return CoverageMetrics(
        observation_coverage=observation_coverage, observation_note=observation_note,
        engineering_coverage=engineering_coverage, engineering_details=details,
        reconstruction_coverage=reconstruction_coverage, reconstruction_note=reconstruction_note,
        reconstruction_details=recon_details,
    )


def corpus_statistics(projects: List[BenchmarkProject]) -> Dict[str, Any]:
    from core.fusion.models import ASPECT_MARK as _M

    stats = {
        "projects": len(projects),
        "drawings_processed": sum(p.drawings_processed for p in projects),
        "observations": sum(len(p.observations) for p in projects),
        "pair_decisions": sum(len(p.decisions) for p in projects),
        "accepted_identities": sum(len(p.identities) for p in projects),
        "ground_truth_identities": sum(len(p.gt_identities) for p in projects),
        "ground_truth_bars": sum(len(p.gt_bars) for p in projects),
        "drawing_roles": {},
        "decision_outcomes": {},
    }
    for p in projects:
        for o in p.observations:
            role = o.drawing_role.role
            stats["drawing_roles"][role] = stats["drawing_roles"].get(role, 0) + 1
        for d in p.decisions:
            stats["decision_outcomes"][d.outcome] = stats["decision_outcomes"].get(d.outcome, 0) + 1
    return stats
