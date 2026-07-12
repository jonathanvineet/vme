"""
Phase 9.3 — Spacing Validation Audit.

Builds full per-gap provenance and per-family statistics for spacing,
instead of the single pooled average-error number `run_phase9.py` reported
previously. Does NOT re-derive geometry: `EngineeringMember.offset_from_representative`
(set in `FamilyBuilder._discover_members`) is already measured correctly —
projected onto the family's own perpendicular axis
(`_ComponentProfile.perp_center`), a signed normal-direction distance, not
raw Euclidean centroid distance. This module organizes and reports that
existing measurement rather than replacing it.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID
import statistics


@dataclass
class SpacingMeasurement:
    family_uuid: UUID
    member_a: UUID
    member_b: UUID
    offset_a: float
    offset_b: float
    measured_spacing: float
    annotated_spacing: Optional[float]
    residual: Optional[float]
    residual_pct: Optional[float]
    is_outlier: bool
    measurement_method: str = "perpendicular_offset_projection"


@dataclass
class FamilySpacingStatistics:
    family_uuid: UUID
    mark: str
    gap_count: int
    reference_spacing: float
    reference_source: str  # 'annotation' or 'inferred_median'
    mean_spacing: float
    median_spacing: float
    rmse: float
    bias: float  # mean signed residual: positive = gaps run wide of reference, negative = narrow
    std_dev: float
    max_abs_error: float
    min_abs_error: float
    outlier_count: int


# A gap's residual (vs. the family's reference spacing) beyond this fraction
# of the reference is flagged as an outlier for the per-gap report — the
# same 35% tolerance already used by FamilyBuilder._select_spacing_sequence
# when deciding whether a candidate belongs to the sequence at all, reused
# here for consistency rather than inventing a second threshold.
OUTLIER_RESIDUAL_FRACTION = 0.35


def measure_family_spacing(family) -> List[SpacingMeasurement]:
    members = sorted(family.members, key=lambda m: m.offset_from_representative)
    annotated = family.annotated_spacing if family.annotated_spacing > 0 else None

    raw_gaps = [
        b.offset_from_representative - a.offset_from_representative
        for a, b in zip(members, members[1:])
    ]
    reference = annotated if annotated is not None else (statistics.median(raw_gaps) if raw_gaps else None)
    tolerance = max(25.0, (reference or 0.0) * OUTLIER_RESIDUAL_FRACTION)

    measurements = []
    for a, b, gap in zip(members, members[1:], raw_gaps):
        residual = (gap - reference) if reference is not None else None
        residual_pct = (residual / reference * 100.0) if reference and residual is not None else None
        is_outlier = residual is not None and abs(residual) > tolerance
        measurements.append(SpacingMeasurement(
            family_uuid=family.uuid,
            member_a=a.component_uuid,
            member_b=b.component_uuid,
            offset_a=round(a.offset_from_representative, 3),
            offset_b=round(b.offset_from_representative, 3),
            measured_spacing=round(gap, 3),
            annotated_spacing=annotated,
            residual=round(residual, 3) if residual is not None else None,
            residual_pct=round(residual_pct, 2) if residual_pct is not None else None,
            is_outlier=is_outlier,
        ))
    return measurements


def compute_family_statistics(family, measurements: List[SpacingMeasurement]) -> Optional[FamilySpacingStatistics]:
    if not measurements:
        return None
    gaps = [m.measured_spacing for m in measurements]
    annotated = measurements[0].annotated_spacing
    reference = annotated if annotated is not None else statistics.median(gaps)
    errors = [g - reference for g in gaps]
    abs_errors = [abs(e) for e in errors]
    rmse = (sum(e ** 2 for e in errors) / len(errors)) ** 0.5
    return FamilySpacingStatistics(
        family_uuid=family.uuid,
        mark=family.mark,
        gap_count=len(gaps),
        reference_spacing=round(reference, 3),
        reference_source="annotation" if annotated is not None else "inferred_median",
        mean_spacing=round(statistics.mean(gaps), 3),
        median_spacing=round(statistics.median(gaps), 3),
        rmse=round(rmse, 3),
        bias=round(statistics.mean(errors), 3),
        std_dev=round(statistics.pstdev(gaps), 3) if len(gaps) > 1 else 0.0,
        max_abs_error=round(max(abs_errors), 3),
        min_abs_error=round(min(abs_errors), 3),
        outlier_count=sum(1 for m in measurements if m.is_outlier),
    )
