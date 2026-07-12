"""
tests/test_phase12_observation_builder.py

Phase 12.1 freeze criteria:
  1. Determinism -- build_observations() produces an identical JSON hash
     across repeated runs on the same directory (same discipline as
     tests/determinism.py for Phases 1-7).
  2. Real-data regression -- SS-GF-01(M).dxf, the only machine-readable
     drawing in test_project/, must yield exactly 3 observations (N4/N6/N7),
     all classified drawing_role='mould_instance' and mark_namespace=
     'reference_code' -- the finding documented in
     docs/research/phase12_cross_view_fusion_research.md Step 1.
  3. Synthetic multi-drawing shape check -- test_project has no real
     second machine-readable drawing yet (see docs/audits/phase12/
     12.1_observation_builder.md), so a hand-built two-drawing fixture
     (one 'R' view with a self-decoding T-mark, one 'M' view with a
     reference-code N-mark) proves build_observations() correctly
     differentiates drawing_role/mark_namespace across drawings before
     any real second drawing is readable.
  4. Guardrail -- PhysicalObservation carries no identity-resolution
     fields. Phase 12.1 must not smuggle in Phase 12.2-12.4 concepts.
  5. Observation invariant -- no fact is ever emitted for an aspect the
     source family didn't actually carry a value for (e.g. a mould-view
     family with no diameter must produce zero DIAMETER facts, not a
     fact with value=None).

Usage:
    python tests/test_phase12_observation_builder.py <directory>

Exit codes:
    0 — all checks passed
    1 — a check failed
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from types import SimpleNamespace
from typing import List


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


def _hash(observations) -> str:
    payload = json.dumps(observations, sort_keys=True, cls=_Encoder)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_determinism(directory: str, runs: int = 5) -> bool:
    from core.full_pipeline import run_pipeline_through_phase9
    from core.fusion.observation_builder import build_observations

    hashes = []
    for _ in range(runs):
        results = list(run_pipeline_through_phase9(directory))
        hashes.append(_hash(build_observations(results)))

    ok = len(set(hashes)) == 1
    print(f"[determinism] {runs} runs -> {'identical' if ok else 'DIVERGED'} ({hashes[0][:12]}...)")
    return ok


def check_real_data_regression(directory: str) -> bool:
    from core.full_pipeline import run_pipeline_through_phase9
    from core.fusion.observation_builder import build_observations
    from core.fusion.models import ASPECT_MARK

    results = list(run_pipeline_through_phase9(directory))
    observations = build_observations(results)

    marks = sorted(o.fact(ASPECT_MARK).value for o in observations if o.fact(ASPECT_MARK))
    roles = {o.drawing_role.role for o in observations}
    namespaces = {o.mark_namespace for o in observations}

    ok = (
        len(observations) == 3
        and marks == ["N4", "N6", "N7"]
        and roles == {"mould_instance"}
        and namespaces == {"reference_code"}
    )
    print(f"[real-data] {len(observations)} observation(s), marks={marks}, "
          f"roles={roles}, namespaces={namespaces} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_synthetic_multi_drawing() -> bool:
    """No real second machine-readable drawing exists yet (see audit doc).
    This builds a minimal two-drawing fixture by hand, entirely in-memory,
    to prove build_observations() differentiates drawing_role and
    mark_namespace across drawings -- the one thing Phase 12.1 exists to
    do -- without waiting on DWG support."""
    from core.fusion.observation_builder import build_observations, NAMESPACE_OBSERVATION
    from core.fusion.models import ASPECT_DIAMETER, ASPECT_MARK
    from core.project import DrawingIdentity, Drawing, DrawingCapabilities, ProjectManifest
    from core.engineering.family import EngineeringFamily, EngineeringMember
    from core.full_pipeline import PipelineResult

    def _member(comp_uuid):
        return EngineeringMember(
            uuid=uuid.uuid4(), component_uuid=comp_uuid, length=1000.0, orientation=0.0,
            layer="S-RBAR", bbox=(0, 0, 1000, 10), centroid=(500, 5), offset_from_representative=0.0,
            confidence=1.0,
        )

    def _family(mark, diameter):
        comp_uuid = uuid.uuid4()
        member = _member(comp_uuid)
        return EngineeringFamily(
            uuid=uuid.uuid4(), mark=mark, diameter=diameter, spacing=0.0,
            annotated_spacing=0.0, inferred_spacing=0.0, spacing_source="none",
            spacing_confidence=0.0, average_spacing_error=0.0, length=1000.0, orientation=0.0,
            dominant_direction=0.0, dominant_direction_label="H", normal_direction=90.0,
            normal_direction_label="V", layer="S-RBAR", recognition_type="straight_bar",
            family_type="main_bar", representative_component=comp_uuid,
            representative_component_uuid=comp_uuid, member_components=[comp_uuid],
            members=[member], member_component_uuids=[comp_uuid], detected_count=1,
            confidence=0.9,
        )

    def _result(filename, view, families):
        identity = DrawingIdentity(
            uuid=uuid.uuid4(), drawing_number="TEST-GF-01", view=view,
            floor="GF", element="TEST", revision="0", confidence=0.9,
        )
        drawing = Drawing(
            identity=identity, filepath=filename, filename=filename, extension=".dxf",
            checksum="", capabilities=DrawingCapabilities(geometry=True),
        )
        manifest = ProjectManifest(
            project_uuid="test", project_name="synthetic", coordinate_system="World",
            units="mm", drawings={filename: drawing},
        )
        return PipelineResult(
            filename=filename, manifest=manifest, canon_repo=None, node_repo=None, graph=None,
            comp_repo=None, entity_by_geom_id={}, recognition_cache=None, plausibility={},
            leader_repo=None, engineering_objects={}, engineering_families=families,
        )

    reinf_result = _result("TEST-GF-01(R).dxf", "R", [_family("T12", 12.0)])
    mould_result = _result("TEST-GF-01(M).dxf", "M", [_family("N7", None)])

    observations = build_observations([reinf_result, mould_result])

    by_mark = {o.fact(ASPECT_MARK).value: o for o in observations if o.fact(ASPECT_MARK)}
    t12, n7 = by_mark.get("T12"), by_mark.get("N7")
    ok = (
        len(observations) == 2
        and t12 is not None and n7 is not None
        and t12.drawing_role.role == "reinforcement_typical"
        and t12.mark_namespace == "self_decoding"
        and t12.fact(ASPECT_DIAMETER) is not None
        and t12.fact(ASPECT_DIAMETER).value == 12.0
        and n7.drawing_role.role == "mould_instance"
        and n7.mark_namespace == "reference_code"
        # observation invariant: N7's family had diameter=None, so it must
        # carry NO diameter fact at all -- not a fact with value=None.
        and n7.fact(ASPECT_DIAMETER) is None
        # UUIDs must be deterministic functions of (filename, family.uuid), not random
        and t12.uuid == uuid.uuid5(
            NAMESPACE_OBSERVATION, f"TEST-GF-01(R).dxf|{reinf_result.engineering_families[0].uuid}"
        )
    )
    print(f"[synthetic] T12->{t12 and t12.drawing_role.role}/{t12 and t12.mark_namespace}, "
          f"N7->{n7 and n7.drawing_role.role}/{n7 and n7.mark_namespace} -> {'OK' if ok else 'MISMATCH'}")
    return ok


def check_no_resolution_leak() -> bool:
    """Guardrail: PhysicalObservation must not carry any Phase 12.2-12.4
    concept (candidates, evidence scores, resolved identity, geometry),
    and must not carry per-aspect flat fields again (mark/diameter/spacing
    as direct attributes) now that facts[] is the single representation."""
    from core.fusion.models import PhysicalObservation

    field_names = {f.name for f in fields(PhysicalObservation)}
    forbidden = {"candidates", "resolved_identity", "identity_uuid", "claims",
                 "centerline", "mesh", "geometry", "evidence_score",
                 "mark", "diameter", "spacing", "shape"}
    leaked = field_names & forbidden
    ok = not leaked
    print(f"[guardrail] PhysicalObservation fields clean of resolution/flat-aspect concepts -> "
          f"{'OK' if ok else 'LEAKED: ' + str(leaked)}")
    return ok


def check_observation_invariant(directory: str) -> bool:
    """'An observation must never infer information it cannot directly
    observe.' Verified two ways: (1) against real data, N6/N7 (whose
    families have no diameter) must carry zero DIAMETER facts; (2) every
    fact's aspect must be one of the declared ASPECT_* constants -- no
    ad-hoc aspect strings sneaking in."""
    from core.full_pipeline import run_pipeline_through_phase9
    from core.fusion.observation_builder import build_observations
    from core.fusion.models import (
        ASPECT_DIAMETER, ASPECT_LENGTH, ASPECT_MARK, ASPECT_ORIENTATION,
        ASPECT_POSITION, ASPECT_QUANTITY, ASPECT_SHAPE, ASPECT_SPACING,
    )

    known_aspects = {ASPECT_MARK, ASPECT_DIAMETER, ASPECT_SPACING, ASPECT_SHAPE,
                      ASPECT_ORIENTATION, ASPECT_POSITION, ASPECT_LENGTH, ASPECT_QUANTITY}

    results = list(run_pipeline_through_phase9(directory))
    observations = build_observations(results)

    no_fabricated_diameter = all(
        o.fact(ASPECT_DIAMETER) is None
        for o in observations
        if o.fact(ASPECT_MARK) and o.fact(ASPECT_MARK).value in ("N6", "N7")
    )
    no_unknown_aspects = all(f.aspect in known_aspects for o in observations for f in o.facts)
    no_none_values = all(f.value is not None for o in observations for f in o.facts)

    ok = no_fabricated_diameter and no_unknown_aspects and no_none_values
    print(f"[invariant] N6/N7 carry no fabricated diameter: {no_fabricated_diameter}; "
          f"all aspects declared: {no_unknown_aspects}; no None-valued facts: {no_none_values} "
          f"-> {'OK' if ok else 'VIOLATED'}")
    return ok


def run_check(directory: str) -> int:
    results = [
        check_determinism(directory),
        check_real_data_regression(directory),
        check_synthetic_multi_drawing(),
        check_no_resolution_leak(),
        check_observation_invariant(directory),
    ]
    if all(results):
        print("\nPHASE 12.1 CHECKS PASSED ✅")
        return 0
    print("\nPHASE 12.1 CHECKS FAILED ❌")
    return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/test_phase12_observation_builder.py <directory>")
        sys.exit(1)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    sys.exit(run_check(sys.argv[1]))
