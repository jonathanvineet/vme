"""
Phase 9.4 — Confidence Decomposition.

Replaces the single opaque family confidence (`EngineeringFamily.confidence`,
a product of member/spacing/completeness terms already computed in
`core/engineering/family.py`) with an explainable, per-dimension breakdown.
Each dimension is scored by an independent provider function that consumes
only its own owning phase's data — geometry sanity, Phase 7 recognition
confidence, Phase 7.6 plausibility decisions, Phase 8 annotation/association
candidate scores, Phase 9.3 spacing statistics, and Phase 9's own
member-discovery agreement — so a low overall score can always be traced to
a specific stage rather than presented as one unexplained number.

`overall` is the geometric mean of the seven dimension scores, not the
arithmetic mean: geometric mean penalizes a single very weak dimension much
more than an average would, matching the intuition that a family is only as
trustworthy as its weakest stage, not the average of its stages.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID


@dataclass
class ConfidenceEvidence:
    dimension: str
    score: float
    explanation: str


@dataclass
class ConfidenceBreakdown:
    family_uuid: UUID
    mark: str
    geometry: float
    recognition: float
    plausibility: float
    annotation: float
    association: float
    spacing: float
    family_consistency: float
    overall: float
    weakest_dimension: str
    evidence: List[ConfidenceEvidence] = field(default_factory=list)


def _geometric_mean(scores: Dict[str, float]) -> float:
    values = [max(s, 1e-6) for s in scores.values()]
    product = 1.0
    for v in values:
        product *= v
    return product ** (1.0 / len(values))


def score_geometry(family) -> ConfidenceEvidence:
    """Owning phase: 2/3/6 (geometry/canonicalization/topology). Sanity of
    the underlying member geometry — not shape correctness (that's
    recognition's job) or physical size (that's plausibility's job), just
    whether the numbers are well-formed."""
    issues = []
    for m in family.members:
        if m.length is None or m.length <= 0:
            issues.append(f"member {m.component_uuid} has non-positive length")
        bb = m.bbox
        if not bb or len(bb) != 4 or any(v != v for v in bb):  # NaN check
            issues.append(f"member {m.component_uuid} has invalid bbox")
    score = 1.0 if not issues else max(0.0, 1.0 - 0.2 * len(issues))
    detail = "All members have valid geometry" if not issues else "; ".join(issues[:3])
    return ConfidenceEvidence("geometry", round(score, 3), detail)


def score_recognition(family, cache) -> ConfidenceEvidence:
    """Owning phase: 7. Mean Phase 7 evidence-based recognizer confidence
    across this family's members (see core/recognition/recognizers.py
    BaseShapeRecognizer._confidence)."""
    confs = []
    for m in family.members:
        res = cache.get(m.component_uuid)
        if res:
            confs.append(res.confidence)
    score = sum(confs) / len(confs) if confs else 0.0
    detail = f"Mean recognizer confidence across {len(confs)} member(s)" if confs else "No recognition data available"
    return ConfidenceEvidence("recognition", round(score, 3), detail)


def score_plausibility(family, plausibility) -> ConfidenceEvidence:
    """Owning phase: 7.6. Physical-plausibility decision across this
    family's members, mapped accept=1.0/review=0.6/reject=0.0 (reject should
    never appear here since those components are excluded from candidacy
    before a family can form — surfaced anyway for transparency if it does)."""
    decision_score = {"accept": 1.0, "review": 0.6, "reject": 0.0}
    scores = []
    flagged = 0
    for m in family.members:
        p = plausibility.get(m.component_uuid)
        if p:
            scores.append(decision_score.get(p.decision, 1.0))
            if p.decision != "accept":
                flagged += 1
    score = sum(scores) / len(scores) if scores else 1.0
    detail = (f"{flagged}/{len(scores)} member(s) flagged by physical plausibility"
              if scores else "No plausibility data (recognition label not evaluated by Phase 7.6)")
    return ConfidenceEvidence("plausibility", round(score, 3), detail)


def score_annotation(family, all_candidates) -> ConfidenceEvidence:
    """Owning phase: 8 (annotation parsing/matching). Strength of the exact
    TOKEN_MARK candidate that seeded this family's mark, for its
    representative component specifically."""
    mark_scores = [
        c.score for c in all_candidates
        if c.token.token_type == "TOKEN_MARK" and c.token.value == family.mark
        and c.component_uuid == family.representative_component_uuid
    ]
    if mark_scores:
        score = max(mark_scores)
        detail = f"Best direct mark-annotation candidate score for representative: {score:.2f}"
    else:
        score = 0.5
        detail = "No direct TOKEN_MARK candidate recorded for the representative component (mark may be inherited via property propagation, not a direct annotation match)"
    return ConfidenceEvidence("annotation", round(score, 3), detail)


def score_association(family, all_candidates) -> ConfidenceEvidence:
    """Owning phase: 8 (engineering association). Mean candidate score
    across ALL tokens (mark, diameter, spacing, length, count) that were
    proposed for this family's representative component, not just the
    winning mark — a broad signal of how confidently Phase 8 tied
    annotations to this specific piece of geometry."""
    rep_scores = [c.score for c in all_candidates if c.component_uuid == family.representative_component_uuid]
    score = sum(rep_scores) / len(rep_scores) if rep_scores else 0.5
    detail = (f"Mean of {len(rep_scores)} association candidate score(s) for the representative component"
              if rep_scores else "No association candidates recorded for the representative component")
    return ConfidenceEvidence("association", round(score, 3), detail)


def score_spacing(family) -> ConfidenceEvidence:
    """Owning phase: 9.3 (spacing validation). Reuses
    EngineeringFamily.spacing_confidence, already computed from measured-gap
    agreement in core/engineering/family.py::_estimate_spacing. Neutral
    (not penalized) for single-member families, where spacing does not
    apply rather than being "bad"."""
    if len(family.members) < 2:
        return ConfidenceEvidence("spacing", 1.0, "Single-member family — spacing not applicable")
    score = family.spacing_confidence
    detail = f"Spacing confidence {score:.2f} from {family.detected_count} member(s), average error {family.average_spacing_error:.1f}mm"
    return ConfidenceEvidence("spacing", round(score, 3), detail)


def score_family_consistency(family) -> ConfidenceEvidence:
    """Owning phase: 9 (family formation). Mean per-member confidence
    already computed during member discovery
    (core/engineering/family.py::_discover_members), which scores
    orientation/length agreement with the family representative."""
    confs = [m.confidence for m in family.members]
    score = sum(confs) / len(confs) if confs else 0.0
    detail = f"Mean member-discovery agreement across {len(confs)} member(s)"
    return ConfidenceEvidence("family_consistency", round(score, 3), detail)


def build_confidence_breakdown(family, cache, plausibility, all_candidates) -> ConfidenceBreakdown:
    dims = {
        "geometry": score_geometry(family),
        "recognition": score_recognition(family, cache),
        "plausibility": score_plausibility(family, plausibility),
        "annotation": score_annotation(family, all_candidates),
        "association": score_association(family, all_candidates),
        "spacing": score_spacing(family),
        "family_consistency": score_family_consistency(family),
    }
    scores = {k: v.score for k, v in dims.items()}
    overall = _geometric_mean(scores)
    weakest = min(scores, key=lambda k: scores[k])
    return ConfidenceBreakdown(
        family_uuid=family.uuid,
        mark=family.mark,
        geometry=scores["geometry"],
        recognition=scores["recognition"],
        plausibility=scores["plausibility"],
        annotation=scores["annotation"],
        association=scores["association"],
        spacing=scores["spacing"],
        family_consistency=scores["family_consistency"],
        overall=round(overall, 3),
        weakest_dimension=weakest,
        evidence=list(dims.values()),
    )
