"""
core/fusion/observation_builder.py — Phase 12.1: Observation Builder.

Turns each drawing's already-frozen Phase 9 output (EngineeringFamily
objects, from core/full_pipeline.py::run_pipeline_through_phase9) into
PhysicalObservation records. This is the ONLY thing Phase 12.1 does.

Implementation Rule #1 (docs/research/phase12_cross_view_fusion_research.md):
the system is forbidden from reconstructing geometry, generating fusion
candidates, or resolving identity in this subphase. The only output is a
flat list of PhysicalObservation. No graph, no mesh, no centerline.

Observation invariant: a fact is only appended for an aspect when the
source family actually carries a real value for it. No aspect is ever
emitted with a placeholder/None value -- absence from `facts` IS "this
observation doesn't know," so there is no separate missing/None state to
track per aspect (see core/fusion/models.py docstring).
"""
from __future__ import annotations

import uuid
from typing import Iterable, List, Optional

from core.fusion.models import (
    ASPECT_DIAMETER, ASPECT_LENGTH, ASPECT_MARK, ASPECT_ORIENTATION,
    ASPECT_POSITION, ASPECT_QUANTITY, ASPECT_SHAPE, ASPECT_SPACING,
    ObservationFact, PhysicalObservation, classify_drawing_role, classify_mark_namespace,
)
from core.full_pipeline import PipelineResult

# Fixed namespace so a PhysicalObservation's UUID is a pure function of
# (drawing filename, family UUID) -- same determinism discipline as every
# other phase in this pipeline (see NAMESPACE_IDENTITY in identity_parser.py).
NAMESPACE_OBSERVATION = uuid.UUID('c9d4a6f1-3b8e-4f2a-9d1c-7e5a2b4f8c33')
# Fixed namespace for ObservationFact UUIDs -- a pure function of
# (observation UUID, aspect), so a fact's identity is stable across runs.
NAMESPACE_FACT = uuid.UUID('e2f7c1b4-5a9d-4e3f-8b6a-1d4c7f9e2a05')

_SOURCE = "family_annotation"


def _facts_for_family(family, obs_uuid, rep_member) -> List[ObservationFact]:
    """Only aspects the family actually carries a real value for. Measured
    geometric aspects (shape/orientation/position/length/quantity) get
    confidence=1.0 -- they're read directly off recognized geometry, not
    inferred -- and a real source_entity_uuid (the representative
    component). Semantic/interpretive aspects (mark/diameter/spacing) that
    depend on Phase 8's annotation-to-geometry association carry that
    association's own confidence instead of a flat 1.0, matching this
    project's established recovery-confidence-vs-engineering-confidence
    split (Phase 9.4 / Phase 10.1) -- and carry source_entity_uuid=None,
    honestly: Phase 8's ConstraintSolver discards the originating
    AnnotationToken.source_uuid (the actual TEXT/MTEXT/DIMENSION entity)
    when it applies a constraint (core/engineering/solver.py::
    ConstraintSolver.solve), so that entity-level provenance isn't
    threaded through to EngineeringFamily today. A real gap, not
    fabricated data -- see docs/audits/phase12/12.2_hypothesis_generator.md."""
    def _fact(aspect, value, confidence, source_entity_uuid=None):
        return ObservationFact(
            uuid=uuid.uuid5(NAMESPACE_FACT, f"{obs_uuid}|{aspect}"),
            aspect=aspect, value=value, confidence=confidence, source=_SOURCE,
            source_entity_uuid=source_entity_uuid,
        )

    facts: List[ObservationFact] = []
    comp_uuid = rep_member.component_uuid if rep_member else None

    if family.mark:
        facts.append(_fact(ASPECT_MARK, family.mark, family.confidence))
    if family.diameter:
        facts.append(_fact(ASPECT_DIAMETER, float(family.diameter), family.confidence))
    if family.spacing:
        facts.append(_fact(ASPECT_SPACING, float(family.spacing), family.spacing_confidence))
    if family.recognition_type:
        facts.append(_fact(ASPECT_SHAPE, family.recognition_type, 1.0, comp_uuid))
    if rep_member is not None:
        facts.append(_fact(ASPECT_ORIENTATION, family.dominant_direction, 1.0, comp_uuid))
        facts.append(_fact(ASPECT_POSITION, tuple(rep_member.centroid), 1.0, comp_uuid))
    if family.length:
        facts.append(_fact(ASPECT_LENGTH, float(family.length), 1.0, comp_uuid))
    if family.detected_count:
        facts.append(_fact(ASPECT_QUANTITY, int(family.detected_count), 1.0, comp_uuid))

    return facts


def build_observations(results: Iterable[PipelineResult]) -> List[PhysicalObservation]:
    """One PhysicalObservation per EngineeringFamily, across all drawings
    in `results`. Deterministic and order-stable: sorted by
    (drawing_filename, mark, family_uuid) so output is hash-comparable
    across runs regardless of dict/set iteration order upstream."""
    observations: List[PhysicalObservation] = []

    for result in results:
        drawing = result.manifest.drawings[result.filename]
        role = classify_drawing_role(drawing.identity.view)

        for family in result.engineering_families:
            obs_uuid = uuid.uuid5(
                NAMESPACE_OBSERVATION, f"{result.filename}|{family.uuid}"
            )
            rep_member = next(
                (m for m in family.members if m.component_uuid == family.representative_component_uuid),
                family.members[0] if family.members else None,
            )
            observations.append(PhysicalObservation(
                uuid=obs_uuid,
                drawing_filename=result.filename,
                drawing_number=drawing.identity.drawing_number,
                drawing_view=drawing.identity.view,
                drawing_role=role,
                family_uuid=family.uuid,
                mark_namespace=classify_mark_namespace(family.mark),
                family_type=family.family_type,
                bbox=tuple(rep_member.bbox) if rep_member else (0.0, 0.0, 0.0, 0.0),
                member_component_uuids=list(family.member_component_uuids),
                facts=_facts_for_family(family, obs_uuid, rep_member),
            ))

    def _mark_for_sort(obs: PhysicalObservation) -> str:
        fact = obs.fact(ASPECT_MARK)
        return fact.value if fact else ""

    observations.sort(key=lambda o: (o.drawing_filename, _mark_for_sort(o), str(o.family_uuid)))
    return observations
